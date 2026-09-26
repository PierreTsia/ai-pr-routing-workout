"""Text and JSON renderings of one routing result."""

from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Any

from pr_route_workout.canvas_view import list_price_cents
from pr_route_workout.facts import make_facts
from pr_route_workout.policies import POLICIES, policy_clauses
from pr_route_workout.run import Result

_RESET = "\033[0m"
_DIM = "\033[2m"
_YELLOW = "\033[33m"
_DISPOSITION_COLOR = {
    "blocked": "\033[31m",
    "needs_author": "\033[31m",
    "ready_for_hitl": "\033[33m",
    "agent_ready": "\033[36m",
    "waiting_for_checks": "\033[36m",
    "ready_for_merge": "\033[32m",
}
_VERDICT_COLOR = {
    "unaddressed": "\033[31m",
    "open": "\033[31m",
    "disputed": "\033[31m",
    "acknowledged": "\033[33m",
    "addressed": "\033[32m",
}


def _facts(result: Result):
    return make_facts(
        author_login=result.pull_request.author,
        checks=result.pull_request.checks,
        draft=result.pull_request.draft,
        jira_keys=result.jira_keys,
        files=result.pull_request.files,
    )


def _pricing(result: Result) -> dict[str, Any]:
    cents = list_price_cents(result.usage)
    billed = 0.0 if result.model and "free" in result.model else cents
    return {
        "list_cents": None if cents is None else round(cents, 3),
        "billed_cents": None if billed is None else round(billed, 3),
    }


def _policy_rows(result: Result) -> list[dict[str, Any]]:
    known = {policy.id: policy for policy in POLICIES}
    matched = set(result.decision.matched_policy_ids)
    rows = [
        {
            "id": policy.id,
            "disposition": policy.disposition.value,
            "matched": policy.id in matched,
        }
        for policy in POLICIES
    ]
    for policy_id in result.decision.matched_policy_ids:
        if policy_id not in known:
            rows.append({"id": policy_id, "disposition": "—", "matched": True})
    return rows


def to_jsonable(result: Result) -> dict[str, Any]:
    pr = result.pull_request
    facts = _facts(result)
    return {
        "pull_request": {
            "repo": pr.repo,
            "number": pr.number,
            "url": pr.url,
            "title": pr.title,
            "author": pr.author,
            "draft": pr.draft,
            "head_sha": pr.head_sha,
            "source": pr.source,
        },
        "facts": {
            "checks": facts.checks.value,
            "check_summary": pr.check_summary,
            "author_is_bot": facts.author_is_bot,
            "jira_keys": list(facts.jira_keys),
            "frontend_code_only": facts.frontend_code_only,
            "touches_frontend_code": facts.touches_frontend_code,
            "dependency_manifest_only": facts.dependency_manifest_only,
            "docs_only": facts.docs_only,
            "ui_path": facts.ui_path,
            "code_suffixes": [
                {"suffix": suffix, "count": count} for suffix, count in facts.code_suffixes
            ],
            "main_code": _main_code(result),
            "path_domains": list(facts.path_domains),
            "primary_domain": _choice(result, "primary_domain"),
            "files": list(facts.files),
            "copilot_tagged": pr.copilot_tagged,
            "copilot_reviewed": pr.copilot_reviewed,
            "claude_tagged": pr.claude_tagged,
            "claude_reviewed": pr.claude_reviewed,
        },
        "review_threads": [
            {
                "id": row.thread_id,
                "path": row.path,
                "url": row.url,
                "verdict": row.verdict,
                "replied": row.replied,
                "unanswered": row.unanswered,
                "outdated": row.outdated,
                "later_commit_sha": row.later_commit_sha,
                "later_commit_touches_path": row.later_commit_touches_path,
                "addressed_noul": row.addressed_noul,
                "stance": row.stance,
                "excerpt": row.excerpt,
                "source": row.source,
            }
            for row in result.thread_rows
        ],
        "disposition": {
            "value": result.decision.disposition.value,
            "policy_id": result.decision.policy_id,
            "matched_policy_ids": list(result.decision.matched_policy_ids),
        },
        "ai_review": {
            "trigger": result.review.trigger,
            "basis": result.review.basis,
            "task": result.review.task,
            "skills": [
                {"id": skill.id, "noul": skill.noul} for skill in result.review.skills
            ],
            "discarded": [
                {"id": skill.id, "noul": skill.noul} for skill in result.review.discarded
            ],
        },
        "judgments": {
            "source": result.judgments,
            "model": result.model,
            "usage": result.usage,
        },
        "pricing": _pricing(result),
        "policies": _policy_rows(result),
        "policy_clauses": [
            {"policy": policy_id, "clause": text, "holds": held}
            for policy_id, text, held in policy_clauses(facts, result.answers)
        ],
        "fan_out": [_fan_out_row(result, question) for question in result.questions],
        "fan_out_truncated": result.fan_out_truncated,
    }


def _fan_out_row(result: Result, question) -> dict[str, Any]:
    answer = None if result.answers is None else result.answers.by_id.get(question.id)
    return {
        "id": question.id,
        "type": question.kind,
        "speculative": question.speculative,
        "choice": None if answer is None else answer.choice,
        "confidence": None if answer is None else answer.confidence,
        "noul": None if answer is None else answer.noul,
        "score": None if answer is None else answer.score,
    }


def _paint(text: str, code: str | None, color: bool) -> str:
    if not color or not code:
        return text
    return f"{code}{text}{_RESET}"


def _fmt(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}"


def _answer_cells(result: Result, question_id: str, kind: str) -> tuple[str, str, bool]:
    answer = None if result.answers is None else result.answers.by_id.get(question_id)
    if answer is None:
        return "—", "—", False
    if kind == "choice":
        return answer.choice or "—", _fmt(answer.confidence), False
    if kind == "noul":
        hot = answer.noul is not None and answer.noul >= 0.6
        return _fmt(answer.noul), "—", hot
    if kind == "score":
        hot = answer.score is not None and answer.score >= 1.5
        return _fmt(answer.score), _fmt(answer.confidence), hot
    return "—", "—", False


def _primitive_lines(result: Result, color: bool) -> list[str]:
    rows = []
    for question in result.questions:
        value, confidence, hot = _answer_cells(result, question.id, question.kind)
        rows.append((question.id, question.kind, value, confidence, hot))
    id_width = max(len("question"), *(len(row[0]) for row in rows))
    kind_width = max(len("kind"), *(len(row[1]) for row in rows))
    value_width = max(len("value"), *(len(row[2]) for row in rows))
    lines = [
        f"  {'question'.ljust(id_width)}  {'kind'.ljust(kind_width)}  {'value'.rjust(value_width)}  confidence"
    ]
    for question_id, kind, value, confidence, hot in rows:
        shown = _paint(value, _YELLOW, color and hot)
        gap = " " * (value_width - len(value))
        lines.append(
            f"  {question_id.ljust(id_width)}  {kind.ljust(kind_width)}  {gap}{shown}  {confidence}"
        )
    return lines


def _thread_lines(result: Result, color: bool) -> list[str]:
    if not result.thread_rows:
        return []
    lines = ["threads"]
    verdict_width = max(len(row.verdict) for row in result.thread_rows)
    for row in result.thread_rows:
        verdict = _paint(row.verdict.ljust(verdict_width), _VERDICT_COLOR.get(row.verdict), color)
        noul = _fmt(row.addressed_noul)
        stance = row.stance or "—"
        later = row.later_commit_sha[:8] if row.later_commit_sha else "—"
        lines.append(
            f"  {row.source.ljust(7)}  {verdict}  {noul}  {stance.ljust(12)}  {later}  {PurePosixPath(row.path).name}"
        )
        if row.excerpt:
            excerpt = row.excerpt if not color else f"{_DIM}{row.excerpt}{_RESET}"
            lines.append(f"    {excerpt}")
    return lines


def _price_line(result: Result) -> str:
    cents = list_price_cents(result.usage)
    billed = 0.0 if result.model and "free" in result.model else cents
    usage = result.usage or {}
    parts = [result.model or result.judgments]
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if isinstance(input_tokens, int) and isinstance(output_tokens, int):
        parts.append(f"{input_tokens} in / {output_tokens} out")
    if cents is not None and billed is not None:
        parts.append(f"list {cents:.3f}¢  billed {billed:.3f}¢")
    return "  ".join(parts)


def _choice(result: Result, question_id: str) -> dict[str, Any] | None:
    if result.answers is None:
        return None
    answer = result.answers.by_id.get(question_id)
    if answer is None or not answer.choice:
        return None
    return {"choice": answer.choice, "confidence": answer.confidence}


def _main_code(result: Result) -> dict[str, Any] | None:
    return _choice(result, "main_code")


def render_text(result: Result, *, color: bool = False) -> str:
    pr = result.pull_request
    facts = _facts(result)
    decision = result.decision
    disposition = decision.disposition.value
    policy = decision.policy_id or "—"
    code = ", ".join(f"{suffix} {count}" for suffix, count in facts.code_suffixes) or "—"
    lines = [
        _paint(
            disposition if decision.policy_id is None else f"{disposition}  {policy}",
            _DISPOSITION_COLOR.get(disposition),
            color,
        ),
        f"{pr.repo}#{pr.number}  {pr.title}",
        pr.url,
        "",
        f"checks   {facts.checks.value}  {pr.check_summary}",
        f"author   {pr.author}" + ("  draft" if pr.draft else ""),
        f"files    {len(facts.files)}  {code}",
        f"domain   {', '.join(facts.path_domains) if facts.path_domains else '—'}",
        f"jira     {', '.join(facts.jira_keys) if facts.jira_keys else '—'}",
        f"ui_path  {str(facts.ui_path).lower()}",
        f"front    {str(facts.touches_frontend_code).lower()}",
        "",
        "primitives",
        *_primitive_lines(result, color),
    ]
    threads = _thread_lines(result, color)
    if threads:
        lines.extend(["", *threads])
    if decision.matched_policy_ids:
        lines.extend(["", "matched  " + ", ".join(decision.matched_policy_ids)])
    if result.review.task:
        lines.append(f"task     {result.review.task}")
    scored_skills = [skill for skill in result.review.skills if skill.noul is not None]
    if scored_skills:
        armed = ", ".join(f"{skill.id} {_fmt(skill.noul)}" for skill in scored_skills)
        lines.append(f"skills   {armed}")
    if result.fan_out_truncated:
        lines.append(f"{result.fan_out_truncated} review threads left out of the fan-out cap")
    lines.extend(["", _price_line(result)])
    if result.judgments == "unavailable":
        lines.append("primitives not scored, no Zen key")
    return "\n".join(lines)


def render_json(result: Result) -> str:
    return json.dumps(to_jsonable(result), indent=2)