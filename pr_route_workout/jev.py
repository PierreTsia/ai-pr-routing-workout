"""One system_one call through the OpenCode Zen proxy, same contract as jev-labyrinth.

The key stays in the environment or in the opencode auth file. No key means the
fan-out is built and not sent. 429 is never retried.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from pr_route_workout.policies import Answer, Answers
from pr_route_workout.questions import Question
from pr_route_workout.reviews import ReviewThread

DEFAULT_URL = "https://opencode.ai/zen/v1/systemone"
DEFAULT_MODEL = "jev-1.13-free"
_BACKOFF_SECONDS = (0.4, 0.8)


class JevError(RuntimeError):
    pass


class RateLimitError(JevError):
    def __init__(self, retry_after_ms: int | None):
        if retry_after_ms is None:
            message = "Jev 429"
        else:
            message = f"Jev 429, retry after {retry_after_ms} ms"
        super().__init__(message)
        self.retry_after_ms = retry_after_ms


def api_key() -> str | None:
    for name in ("OPENCODE_API_KEY", "ZEN_API_KEY", "TYPESAFE_API_KEY", "JEV_API_KEY"):
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return _key_from_opencode_auth()


def _key_from_opencode_auth() -> str | None:
    configured = os.environ.get("OPENCODE_AUTH_FILE")
    path = Path(configured) if configured else Path.home() / ".local/share/opencode/auth.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    for name in ("zen", "opencode", "opencode-zen", "opencode-go"):
        found = _provider_key(data.get(name))
        if found:
            return found
    for value in data.values():
        found = _provider_key(value)
        if found:
            return found
    return None


def _provider_key(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        for field in ("key", "apiKey", "token"):
            item = value.get(field)
            if isinstance(item, str) and item.strip():
                return item.strip()
    return None


def build_state(
    pr_title: str,
    pr_body: str,
    pr_author: str,
    files: tuple[str, ...],
    diff_stat: str,
    patch_excerpt: str,
    jira_keys: tuple[str, ...],
    threads: tuple[ReviewThread, ...] = (),
) -> dict[str, Any]:
    return {
        "pull_request": {
            "title": pr_title,
            "body": pr_body[:4000],
            "author": pr_author,
            "files": list(files),
            "diff_stat": diff_stat,
            "patch_excerpt": patch_excerpt,
        },
        # Issue text is not fetched. The key list is a fact; the match Noul is not asked.
        "jira": None,
        "jira_keys": list(jira_keys),
        "review_threads": [
            {
                "id": thread.id,
                "path": thread.path,
                "outdated": thread.outdated,
                "source": thread.source,
                "later_commit": thread.later_commit_sha,
                "comments": [
                    {
                        "author": comment.author,
                        "at": comment.created_at,
                        "body": comment.body[:800],
                    }
                    for comment in thread.comments
                ],
            }
            for thread in threads
            if thread.tracked
        ],
    }


def request_body(
    state: dict[str, Any] | str,
    questions: tuple[Question, ...],
    model: str | None = None,
) -> dict[str, Any]:
    """Zen accepts a string state. Structured input is JSON, not a nested object."""
    encoded = state if isinstance(state, str) else json.dumps(state, ensure_ascii=False)
    return {
        "model": model or os.environ.get("JEV_MODEL") or DEFAULT_MODEL,
        "state": encoded,
        "questions": {question.id: question.to_api() for question in questions},
    }


def decide(
    state: dict[str, Any] | str,
    questions: tuple[Question, ...],
    *,
    key: str,
    model: str | None = None,
    url: str | None = None,
    opener: Callable[..., Any] = urllib.request.urlopen,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    body = request_body(state, questions, model)
    endpoint = url or os.environ.get("JEV_API_URL") or DEFAULT_URL
    payload = json.dumps(body).encode("utf-8")
    attempts = len(_BACKOFF_SECONDS) + 1
    for attempt in range(attempts):
        request = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "User-Agent": "pr-route-workout",
            },
            method="POST",
        )
        try:
            with opener(request, timeout=60) as response:
                parsed = json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            if exc.code == 429:
                raise RateLimitError(_retry_after_ms(exc.headers)) from exc
            if 400 <= exc.code < 500 or attempt == attempts - 1:
                raise JevError(f"Jev {exc.code}: {detail}") from exc
            sleeper(_BACKOFF_SECONDS[attempt])
            continue
        except urllib.error.URLError as exc:
            if attempt == attempts - 1:
                raise JevError(f"Jev network error: {exc.reason}") from exc
            sleeper(_BACKOFF_SECONDS[attempt])
            continue
        if not isinstance(parsed, dict):
            raise JevError("Jev returned a non-object response")
        return parsed
    raise JevError("Jev request failed")


def _retry_after_ms(headers: Any) -> int | None:
    if headers is None:
        return None
    raw = headers.get("Retry-After") if hasattr(headers, "get") else None
    if raw is None:
        return None
    try:
        return int(float(raw) * 1000)
    except ValueError:
        return None


def answers_from_payload(payload: dict[str, Any], questions: tuple[Question, ...]) -> Answers:
    raw = payload.get("answers")
    if not isinstance(raw, dict):
        raise JevError("Jev response has no answers object")
    by_id: dict[str, Answer] = {}
    for question in questions:
        item = raw.get(question.id)
        if not isinstance(item, dict):
            raise JevError(f"Jev response missing answer for {question.id}")
        kind = item.get("type", question.kind)
        if kind != question.kind:
            raise JevError(f"{question.id} came back as {kind}, asked as {question.kind}")
        by_id[question.id] = Answer(
            kind=kind,
            choice=item.get("choice"),
            confidence=item.get("confidence"),
            noul=item.get("noul"),
            score=item.get("score"),
        )
    return Answers(by_id)