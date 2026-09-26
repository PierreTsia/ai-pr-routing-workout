"""Read one pull request from GitHub. Public repos need no token."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass

from pr_route_workout.facts import CheckStatus, interpret_checks
from pr_route_workout.reviews import Commit, ReviewThread, build_threads, is_claude, is_copilot, is_human_reviewer

API = "https://api.github.com"
USER_AGENT = "pr-route-workout"
PATCH_BUDGET = 8_000
MAX_FILE_PAGES = 3


class GitHubError(RuntimeError):
    pass


@dataclass(frozen=True)
class PullRequest:
    repo: str
    number: int
    url: str
    title: str
    body: str
    author: str
    draft: bool
    head_sha: str
    files: tuple[str, ...]
    diff_stat: str
    patch_excerpt: str
    checks: CheckStatus
    check_summary: str
    source: str  # github or fixture
    labels: tuple[str, ...] = ()
    requested_reviewers: tuple[str, ...] = ()
    copilot_tagged: bool = False
    copilot_reviewed: bool = False
    claude_tagged: bool = False
    claude_reviewed: bool = False
    threads: tuple[ReviewThread, ...] = ()


def parse_ref(ref: str, number: int | None = None) -> tuple[str, int]:
    text = ref.strip().rstrip("/")
    if text.startswith("https://github.com/") or text.startswith("http://github.com/"):
        parts = text.split("github.com/", 1)[1].split("/")
        if len(parts) >= 4 and parts[2] == "pull" and parts[3].isdigit():
            return f"{parts[0]}/{parts[1]}", int(parts[3])
        raise GitHubError(f"not a pull request url: {ref}")
    if "#" in text and number is None:
        repo, _, raw = text.partition("#")
        if "/" in repo and raw.isdigit():
            return repo, int(raw)
        raise GitHubError(f"expected owner/repo#N, got {ref}")
    if number is None:
        raise GitHubError("pass a url, owner/repo#N, or owner/repo and a number")
    if "/" not in text:
        raise GitHubError(f"expected owner/repo, got {ref}")
    return text, number


def _token() -> str | None:
    for name in ("GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return _gh_cli_token()


def _gh_cli_token() -> str | None:
    try:
        completed = subprocess.run(
            ["gh", "auth", "token"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    token = completed.stdout.strip()
    return token or None


def _request(url: str, token: str | None) -> tuple[dict | list, dict[str, str]]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
            headers = {key.lower(): value for key, value in response.headers.items()}
            return payload, headers
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        if exc.code in {401, 403, 404}:
            hint = ""
            if not token:
                hint = " Set GH_TOKEN (or GITHUB_TOKEN) for a private repo."
            raise GitHubError(f"GitHub {exc.code} on {url}.{hint} {detail}") from exc
        raise GitHubError(f"GitHub {exc.code} on {url}. {detail}") from exc


def _files(repo: str, number: int, token: str | None) -> list[dict]:
    collected: list[dict] = []
    url = f"{API}/repos/{repo}/pulls/{number}/files?per_page=100"
    for _ in range(MAX_FILE_PAGES):
        payload, headers = _request(url, token)
        if not isinstance(payload, list):
            raise GitHubError(f"unexpected file list from {url}")
        collected.extend(payload)
        link = headers.get("link", "")
        next_url = _next_link(link)
        if not next_url:
            return collected
        url = next_url
    return collected


def _next_link(link: str) -> str | None:
    for part in link.split(","):
        if 'rel="next"' in part:
            return part.split(";")[0].strip().strip("<>")
    return None


def _patch_excerpt(files: list[dict]) -> str:
    chunks: list[str] = []
    used = 0
    for item in files:
        patch = item.get("patch")
        if not patch:
            continue
        header = f"--- {item['filename']}\n"
        room = PATCH_BUDGET - used - len(header)
        if room <= 0:
            break
        piece = patch[:room]
        chunks.append(header + piece)
        used += len(header) + len(piece)
    return "\n".join(chunks)


def _diff_stat(pr: dict, files: list[dict]) -> str:
    lines = [
        f"{pr.get('changed_files', len(files))} files, +{pr.get('additions', 0)} -{pr.get('deletions', 0)}"
    ]
    for item in files[:40]:
        lines.append(
            f"{item['filename']} | +{item.get('additions', 0)} -{item.get('deletions', 0)}"
        )
    if len(files) > 40:
        lines.append(f"... {len(files) - 40} more files")
    return "\n".join(lines)


def fetch_pull_request(repo: str, number: int) -> PullRequest:
    token = _token()
    payload, _headers = _request(f"{API}/repos/{repo}/pulls/{number}", token)
    if not isinstance(payload, dict):
        raise GitHubError(f"unexpected pull request payload for {repo}#{number}")
    files = _files(repo, number, token)
    sha = payload["head"]["sha"]
    runs_payload, _runs_headers = _request(
        f"{API}/repos/{repo}/commits/{sha}/check-runs?per_page=100",
        token,
    )
    if not isinstance(runs_payload, dict):
        raise GitHubError(f"unexpected check runs for {sha}")
    check_runs = list(runs_payload.get("check_runs") or [])
    total = int(runs_payload.get("total_count") or len(check_runs))
    combined_state = None
    if total == 0:
        status_payload, _status_headers = _request(
            f"{API}/repos/{repo}/commits/{sha}/status",
            token,
        )
        if isinstance(status_payload, dict):
            combined_state = status_payload.get("state")
    checks, summary = interpret_checks(
        check_runs,
        combined_state,
        truncated=total > len(check_runs),
    )
    review_comments = _paged_list(f"{API}/repos/{repo}/pulls/{number}/comments?per_page=100", token)
    review_summaries = _paged_list(f"{API}/repos/{repo}/pulls/{number}/reviews?per_page=100", token)
    commit_rows = _paged_list(f"{API}/repos/{repo}/pulls/{number}/commits?per_page=100", token)
    commits = [
        Commit(
            sha=row["sha"],
            committed_at=(row.get("commit") or {}).get("committer", {}).get("date") or "",
            summary=((row.get("commit") or {}).get("message") or "").split("\n", 1)[0][:120],
        )
        for row in commit_rows
        if isinstance(row, dict) and row.get("sha")
    ]
    author = payload["user"]["login"]
    paths_by_sha = _paths_for_later_commits(repo, commits, review_comments, token, author)
    threads = build_threads(review_comments, commits, paths_by_sha, pull_author=author)
    labels = tuple(
        label.get("name") or ""
        for label in payload.get("labels") or []
        if isinstance(label, dict)
    )
    requested = tuple(
        user.get("login") or ""
        for user in payload.get("requested_reviewers") or []
        if isinstance(user, dict)
    )
    copilot_tagged = any("copilot" in label.lower() for label in labels) or any(
        is_copilot(login) for login in requested
    )
    copilot_reviewed = any(
        is_copilot((review.get("user") or {}).get("login"))
        for review in review_summaries
        if isinstance(review, dict)
    ) or any(thread.copilot for thread in threads)
    claude_tagged = any("claude" in label.lower() for label in labels) or any(
        is_claude(login) for login in requested
    )
    claude_reviewed = any(
        is_claude((review.get("user") or {}).get("login"))
        for review in review_summaries
        if isinstance(review, dict)
    ) or any(thread.claude for thread in threads)
    return PullRequest(
        repo=repo,
        number=number,
        url=payload["html_url"],
        title=payload.get("title") or "",
        body=payload.get("body") or "",
        author=author,
        draft=bool(payload.get("draft")),
        head_sha=sha,
        files=tuple(item["filename"] for item in files),
        diff_stat=_diff_stat(payload, files),
        patch_excerpt=_patch_excerpt(files),
        checks=checks,
        check_summary=summary,
        source="github",
        labels=labels,
        requested_reviewers=requested,
        copilot_tagged=copilot_tagged,
        copilot_reviewed=copilot_reviewed,
        claude_tagged=claude_tagged,
        claude_reviewed=claude_reviewed,
        threads=threads,
    )


def _paged_list(url: str, token: str | None, pages: int = 2) -> list[dict]:
    collected: list[dict] = []
    for _ in range(pages):
        payload, headers = _request(url, token)
        if not isinstance(payload, list):
            raise GitHubError(f"unexpected list from {url}")
        collected.extend(item for item in payload if isinstance(item, dict))
        nxt = _next_link(headers.get("link", ""))
        if not nxt:
            return collected
        url = nxt
    return collected


def _paths_for_later_commits(
    repo: str,
    commits: list[Commit],
    comments: list[dict],
    token: str | None,
    pull_author: str,
) -> dict[str, frozenset[str] | None]:
    anchors = [
        comment.get("created_at") or ""
        for comment in comments
        if _is_review_anchor((comment.get("user") or {}).get("login"), pull_author)
    ]
    if not anchors:
        return {}
    earliest = min(anchors)
    later = [commit for commit in commits if commit.committed_at > earliest][:15]
    paths: dict[str, frozenset[str] | None] = {}
    for commit in later:
        payload, _headers = _request(f"{API}/repos/{repo}/commits/{commit.sha}", token)
        if not isinstance(payload, dict):
            paths[commit.sha] = None
            continue
        files = payload.get("files") or []
        paths[commit.sha] = frozenset(
            item.get("filename") or "" for item in files if isinstance(item, dict)
        )
    return paths


def _is_review_anchor(login: str | None, pull_author: str) -> bool:
    return is_copilot(login) or is_claude(login) or is_human_reviewer(login, pull_author)