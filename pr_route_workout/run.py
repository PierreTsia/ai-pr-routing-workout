"""Wire a pull request to facts, an optional Jev call, policies, and skills."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pr_route_workout.facts import make_facts
from pr_route_workout.github import PullRequest
from pr_route_workout.jev import answers_from_payload, api_key, build_state, decide
from pr_route_workout.policies import (
    AiReview,
    Answers,
    Decision,
    ThreadVerdict,
    ai_review,
    apply_copilot,
    route,
    thread_verdicts,
)
from pr_route_workout.questions import Question, build_questions
from pr_route_workout.reviews import threads_for_fan_out


@dataclass(frozen=True)
class Result:
    pull_request: PullRequest
    decision: Decision
    review: AiReview
    questions: tuple[Question, ...]
    judgments: str  # unavailable or zen
    model: str | None
    usage: dict[str, Any] | None
    jira_keys: tuple[str, ...]
    thread_rows: tuple[ThreadVerdict, ...]
    fan_out_truncated: int
    answers: Answers | None = None


def evaluate(pr: PullRequest, *, allow_projects: frozenset[str] | None = None) -> Result:
    keys = pr_jira_keys(pr, allow_projects)
    facts = make_facts(
        author_login=pr.author,
        checks=pr.checks,
        draft=pr.draft,
        jira_keys=keys,
        files=pr.files,
    )
    judged = threads_for_fan_out(pr.threads)
    questions = build_questions(pr.threads)
    answers: Answers | None = None
    model = None
    usage = None
    judgments = "unavailable"
    key = api_key()
    if key:
        state = build_state(
            pr.title,
            pr.body,
            pr.author,
            pr.files,
            pr.diff_stat,
            pr.patch_excerpt,
            keys,
            pr.threads,
        )
        payload = decide(state, questions, key=key)
        answers = answers_from_payload(payload, questions)
        model = payload.get("model") if isinstance(payload.get("model"), str) else None
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else None
        judgments = "zen"
    decision = apply_copilot(route(facts, answers), pr.threads, answers)
    review = ai_review(facts, answers, decision)
    tracked_count = sum(1 for thread in pr.threads if thread.tracked)
    return Result(
        pull_request=pr,
        decision=decision,
        review=review,
        questions=questions,
        judgments=judgments,
        model=model,
        usage=usage,
        jira_keys=keys,
        thread_rows=thread_verdicts(pr.threads, answers),
        fan_out_truncated=max(0, tracked_count - len(judged)),
        answers=answers,
    )


def pr_jira_keys(pr: PullRequest, allow_projects: frozenset[str] | None) -> tuple[str, ...]:
    from pr_route_workout.facts import issue_keys

    return issue_keys(pr.title, pr.body, allow_projects=allow_projects)