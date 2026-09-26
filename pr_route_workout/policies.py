"""Policies are data. Severity is an explicit rank, not the enum's integer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from pr_route_workout.facts import CheckStatus, Facts, is_frontend_code
from pr_route_workout.questions import SKILL_NOUL_THRESHOLD, SKILLS, Question, Skill
from pr_route_workout.reviews import ReviewThread, threads_for_fan_out


class Disposition(Enum):
    READY_FOR_MERGE = "ready_for_merge"
    WAITING_FOR_CHECKS = "waiting_for_checks"
    READY_FOR_HITL = "ready_for_hitl"
    AGENT_READY = "agent_ready"
    NEEDS_AUTHOR = "needs_author"
    BLOCKED = "blocked"


SEVERITY: dict[Disposition, int] = {
    Disposition.READY_FOR_MERGE: 0,
    Disposition.WAITING_FOR_CHECKS: 1,
    Disposition.READY_FOR_HITL: 2,
    Disposition.AGENT_READY: 3,
    Disposition.NEEDS_AUTHOR: 4,
    Disposition.BLOCKED: 5,
}


class AnswerView(Protocol):
    def get(self, question_id: str) -> "Answer": ...


@dataclass(frozen=True)
class Answer:
    kind: str
    choice: str | None = None
    confidence: float | None = None
    noul: float | None = None
    score: float | None = None


@dataclass(frozen=True)
class Answers:
    by_id: dict[str, Answer]

    def get(self, question_id: str) -> Answer:
        try:
            return self.by_id[question_id]
        except KeyError as exc:
            raise KeyError(f"fan-out has no answer for {question_id}") from exc


class Clause(Protocol):
    def holds(self, facts: Facts, answers: Answers | None) -> bool: ...


@dataclass(frozen=True)
class FactIs:
    name: str
    value: object

    def holds(self, facts: Facts, answers: Answers | None) -> bool:
        return getattr(facts, self.name) == self.value


@dataclass(frozen=True)
class NoJiraKey:
    def holds(self, facts: Facts, answers: Answers | None) -> bool:
        return len(facts.jira_keys) == 0


@dataclass(frozen=True)
class _Judgment:
    question: str
    kind: str

    def _read(self, answers: Answers | None) -> Answer | None:
        if answers is None:
            return None
        found = answers.get(self.question)
        if found.kind != self.kind:
            raise TypeError(
                f"{self.question} is a {found.kind}, this clause reads a {self.kind}"
            )
        return found


@dataclass(frozen=True)
class ChoiceIn(_Judgment):
    options: frozenset[str]

    def __init__(self, question: str, options: frozenset[str]):
        object.__setattr__(self, "question", question)
        object.__setattr__(self, "kind", "choice")
        object.__setattr__(self, "options", options)

    def holds(self, facts: Facts, answers: Answers | None) -> bool:
        found = self._read(answers)
        return found is not None and found.choice in self.options


@dataclass(frozen=True)
class ScoreAtLeast(_Judgment):
    threshold: float

    def __init__(self, question: str, threshold: float):
        object.__setattr__(self, "question", question)
        object.__setattr__(self, "kind", "score")
        object.__setattr__(self, "threshold", threshold)

    def holds(self, facts: Facts, answers: Answers | None) -> bool:
        found = self._read(answers)
        return found is not None and found.score is not None and found.score >= self.threshold


@dataclass(frozen=True)
class ScoreBelow(_Judgment):
    threshold: float

    def __init__(self, question: str, threshold: float):
        object.__setattr__(self, "question", question)
        object.__setattr__(self, "kind", "score")
        object.__setattr__(self, "threshold", threshold)

    def holds(self, facts: Facts, answers: Answers | None) -> bool:
        found = self._read(answers)
        return found is not None and found.score is not None and found.score < self.threshold


@dataclass(frozen=True)
class NoulAtLeast(_Judgment):
    threshold: float

    def __init__(self, question: str, threshold: float):
        object.__setattr__(self, "question", question)
        object.__setattr__(self, "kind", "noul")
        object.__setattr__(self, "threshold", threshold)

    def holds(self, facts: Facts, answers: Answers | None) -> bool:
        found = self._read(answers)
        return found is not None and found.noul is not None and found.noul >= self.threshold


@dataclass(frozen=True)
class ConfidenceBelow(_Judgment):
    threshold: float

    def __init__(self, question: str, threshold: float):
        object.__setattr__(self, "question", question)
        object.__setattr__(self, "kind", "choice")
        object.__setattr__(self, "threshold", threshold)

    def holds(self, facts: Facts, answers: Answers | None) -> bool:
        found = self._read(answers)
        return (
            found is not None
            and found.confidence is not None
            and found.confidence < self.threshold
        )


@dataclass(frozen=True)
class All:
    clauses: tuple[Clause, ...]

    def holds(self, facts: Facts, answers: Answers | None) -> bool:
        return all(clause.holds(facts, answers) for clause in self.clauses)


@dataclass(frozen=True)
class Any:
    clauses: tuple[Clause, ...]

    def holds(self, facts: Facts, answers: Answers | None) -> bool:
        return any(clause.holds(facts, answers) for clause in self.clauses)


def _clause_text(clause: Clause) -> str:
    if isinstance(clause, FactIs):
        value = clause.value.value if isinstance(clause.value, Enum) else clause.value
        return f"{clause.name} = {value}"
    if isinstance(clause, NoJiraKey):
        return "jira_keys empty"
    if isinstance(clause, ChoiceIn):
        options = ", ".join(sorted(clause.options))
        return f"{clause.question} in {{{options}}}"
    if isinstance(clause, ScoreAtLeast):
        return f"{clause.question} >= {clause.threshold}"
    if isinstance(clause, ScoreBelow):
        return f"{clause.question} < {clause.threshold}"
    if isinstance(clause, NoulAtLeast):
        return f"{clause.question} >= {clause.threshold}"
    if isinstance(clause, ConfidenceBelow):
        return f"{clause.question} confidence < {clause.threshold}"
    return type(clause).__name__


def _leaves(clause: Clause) -> tuple[Clause, ...]:
    if isinstance(clause, (All, Any)):
        found: list[Clause] = []
        for child in clause.clauses:
            found.extend(_leaves(child))
        return tuple(found)
    return (clause,)


def policy_clauses(
    facts: Facts, answers: Answers | None
) -> tuple[tuple[str, str, bool], ...]:
    rows: list[tuple[str, str, bool]] = []
    for policy in POLICIES:
        for leaf in _leaves(policy.when):
            rows.append((policy.id, _clause_text(leaf), leaf.holds(facts, answers)))
    return tuple(rows)


@dataclass(frozen=True)
class Policy:
    id: str
    disposition: Disposition
    when: Clause
    task: str | None = None


@dataclass(frozen=True)
class AgentJob:
    id: str
    skill_id: str
    task: str


AGENT_JOBS: tuple[AgentJob, ...] = (
    AgentJob("tdd_job", "tdd", "Pass tdd on {files}."),
    AgentJob("microcopy_job", "microcopy", "Pass microcopy on {files}."),
    AgentJob("epic_brief_job", "epic-brief", "Pass epic-brief on {files}."),
    AgentJob("tech_plan_job", "tech-plan", "Pass tech-plan on {files}."),
    AgentJob("achievement_job", "new-achievement-track", "Pass new-achievement-track on {files}."),
    AgentJob("pr_review_job", "pr-review", "Pass pr-review on {files}."),
    AgentJob("blog_post_job", "blog-post", "Pass blog-post on {files}."),
    AgentJob("split_tickets_job", "split-tickets", "Pass split-tickets on {files}."),
)

_SKILL_BY_ID = {skill.id: skill for skill in SKILLS}
_JOB_BY_ID = {job.id: job for job in AGENT_JOBS}


def _frontend_job(job: AgentJob) -> Policy:
    skill = _SKILL_BY_ID[job.skill_id]
    return Policy(
        id=job.id,
        disposition=Disposition.AGENT_READY,
        task=job.task,
        when=All(
            (
                FactIs("touches_frontend_code", True),
                NoulAtLeast(skill.question_id, SKILL_NOUL_THRESHOLD),
                ScoreBelow("review_depth", 1.5),
                ScoreBelow("blast_radius", 1.5),
            )
        ),
    )


POLICIES: tuple[Policy, ...] = (
    Policy(
        id="failing_checks",
        disposition=Disposition.BLOCKED,
        when=All((FactIs("checks", CheckStatus.FAILED),)),
    ),
    Policy(
        id="bot_manifest_green",
        disposition=Disposition.READY_FOR_MERGE,
        when=All(
            (
                FactIs("author_is_bot", True),
                FactIs("draft", False),
                FactIs("checks", CheckStatus.GREEN),
                FactIs("dependency_manifest_only", True),
            )
        ),
    ),
    Policy(
        id="nontrivial_without_issue",
        disposition=Disposition.NEEDS_AUTHOR,
        when=All(
            (
                NoJiraKey(),
                FactIs("dependency_manifest_only", False),
                FactIs("docs_only", False),
            )
        ),
    ),
    *(_frontend_job(job) for job in AGENT_JOBS),
    Policy(
        id="feature_or_migration",
        disposition=Disposition.READY_FOR_HITL,
        when=Any(
            (
                ChoiceIn("change_shape", frozenset({"feature", "migration"})),
                ScoreAtLeast("review_depth", 1.5),
                ScoreAtLeast("blast_radius", 1.5),
                ConfidenceBelow("change_shape", 0.6),
            )
        ),
    ),
)


@dataclass(frozen=True)
class Decision:
    disposition: Disposition
    policy_id: str | None
    matched_policy_ids: tuple[str, ...]


def route(facts: Facts, answers: Answers | None) -> Decision:
    matched = [policy for policy in POLICIES if policy.when.holds(facts, answers)]
    if not matched:
        if facts.checks == CheckStatus.PENDING:
            return Decision(Disposition.WAITING_FOR_CHECKS, None, ())
        return Decision(Disposition.READY_FOR_HITL, None, ())
    winner = max(matched, key=lambda policy: SEVERITY[policy.disposition])
    return Decision(
        winner.disposition,
        winner.id,
        tuple(policy.id for policy in matched),
    )


@dataclass(frozen=True)
class SkillScore:
    id: str
    noul: float | None


@dataclass(frozen=True)
class AiReview:
    trigger: bool
    basis: str
    skills: tuple[SkillScore, ...]
    discarded: tuple[SkillScore, ...]
    task: str | None = None


def _skill_score(skill: Skill, answers: Answers | None) -> SkillScore:
    if answers is None:
        return SkillScore(skill.id, None)
    return SkillScore(skill.id, answers.get(skill.question_id).noul)


def _frontend_files(facts: Facts) -> str:
    files = [path for path in facts.files if is_frontend_code(path)]
    return ", ".join(files) if files else "the changed frontend files"


def _filled_task(policy: Policy, facts: Facts) -> str:
    return (policy.task or "").replace("{files}", _frontend_files(facts))


def _idle_basis(facts: Facts) -> str:
    if facts.dependency_manifest_only and facts.ui_path:
        return "UI package path, but the diff is only a dependency manifest"
    if facts.dependency_manifest_only:
        return "dependency manifest only"
    if not facts.touches_frontend_code:
        return "not frontend code"
    return "no closed frontend job matched"


def ai_review(facts: Facts, answers: Answers | None, decision: Decision) -> AiReview:
    scored = tuple(_skill_score(skill, answers) for skill in SKILLS)
    if answers is None:
        return AiReview(False, f"{_idle_basis(facts)}; skills not scored", (), ())
    if decision.disposition != Disposition.AGENT_READY:
        return AiReview(False, _idle_basis(facts), (), scored)

    armed_ids = frozenset(
        _JOB_BY_ID[policy_id].skill_id
        for policy_id in decision.matched_policy_ids
        if policy_id in _JOB_BY_ID
    )
    armed = tuple(skill for skill in scored if skill.id in armed_ids)
    dropped = tuple(skill for skill in scored if skill.id not in armed_ids)
    policy = next(item for item in POLICIES if item.id == decision.policy_id)
    task = _filled_task(policy, facts)
    return AiReview(True, task, armed, dropped, task=task)


def judgment_question_ids(questions: tuple[Question, ...]) -> frozenset[str]:
    return frozenset(question.id for question in questions)


ADDRESSED_NOUL = 0.6


@dataclass(frozen=True)
class ThreadVerdict:
    thread_id: int
    path: str
    excerpt: str
    url: str
    replied: bool
    unanswered: bool
    outdated: bool
    later_commit_sha: str | None
    later_commit_touches_path: bool | None
    addressed_noul: float | None
    stance: str | None
    verdict: str
    source: str


def _excerpt(text: str, limit: int = 140) -> str:
    return " ".join(text.split())[:limit]


def thread_verdicts(
    threads: tuple[ReviewThread, ...],
    answers: Answers | None,
) -> tuple[ThreadVerdict, ...]:
    judged = {thread.id for thread in threads_for_fan_out(threads)}
    rows: list[ThreadVerdict] = []
    for thread in threads:
        if not thread.tracked:
            continue
        root = thread.comments[0]
        source = thread.source
        addressed_noul = None
        stance = None
        if answers is not None and thread.id in judged:
            addressed_noul = answers.get(f"thread_{thread.id}_addressed").noul
            stance = answers.get(f"thread_{thread.id}_stance").choice
            verdict = _scored_verdict(stance, addressed_noul)
        elif thread.unanswered:
            verdict = "open"
        elif thread.replied and thread.later_commit_sha:
            verdict = "replied_and_commit_unscored"
        elif thread.replied:
            verdict = "replied_unscored"
        elif thread.later_commit_sha:
            verdict = "commit_after_unscored"
        else:
            verdict = "open"
        rows.append(
            ThreadVerdict(
                thread_id=thread.id,
                path=thread.path,
                excerpt=_excerpt(root.body),
                url=root.url,
                replied=thread.replied,
                unanswered=thread.unanswered,
                outdated=thread.outdated,
                later_commit_sha=thread.later_commit_sha,
                later_commit_touches_path=thread.later_commit_touches_path,
                addressed_noul=addressed_noul,
                stance=stance,
                verdict=verdict,
                source=source,
            )
        )
    return tuple(rows)


def _scored_verdict(stance: str | None, addressed_noul: float | None) -> str:
    if stance == "addressed" and addressed_noul is not None and addressed_noul >= ADDRESSED_NOUL:
        return "addressed"
    if stance == "disputed":
        return "disputed"
    if stance == "acknowledged":
        return "acknowledged"
    return "unaddressed"


_THREAD_POLICIES: dict[str, tuple[str, str, str, str]] = {
    "copilot": (
        "copilot_thread_unanswered",
        "copilot_followup_unscored",
        "copilot_comment_unaddressed",
        "copilot_comment_needs_human",
    ),
    "claude": (
        "claude_thread_unanswered",
        "claude_followup_unscored",
        "claude_comment_unaddressed",
        "claude_comment_needs_human",
    ),
    "human": (
        "review_thread_unanswered",
        "review_followup_unscored",
        "review_comment_unaddressed",
        "review_comment_needs_human",
    ),
}


def _matches_for_source(
    rows: tuple[ThreadVerdict, ...],
    answers: Answers | None,
    policy_ids: tuple[str, str, str, str],
) -> tuple[tuple[str, Disposition], ...]:
    open_id, unscored_id, unaddressed_id, needs_human_id = policy_ids
    if not rows:
        return ()
    matches: list[tuple[str, Disposition]] = []
    if answers is None:
        if any(row.verdict == "open" for row in rows):
            matches.append((open_id, Disposition.NEEDS_AUTHOR))
        if any(row.verdict.endswith("unscored") for row in rows):
            matches.append((unscored_id, Disposition.READY_FOR_HITL))
        return tuple(matches)
    if any(row.verdict == "unaddressed" for row in rows):
        matches.append((unaddressed_id, Disposition.NEEDS_AUTHOR))
    if any(row.verdict in {"disputed", "acknowledged"} for row in rows):
        matches.append((needs_human_id, Disposition.READY_FOR_HITL))
    return tuple(matches)


def copilot_matches(
    threads: tuple[ReviewThread, ...],
    answers: Answers | None,
) -> tuple[tuple[str, Disposition], ...]:
    verdicts = thread_verdicts(threads, answers)
    if not verdicts:
        return ()
    matches: list[tuple[str, Disposition]] = []
    for source, policy_ids in _THREAD_POLICIES.items():
        rows = tuple(row for row in verdicts if row.source == source)
        matches.extend(_matches_for_source(rows, answers, policy_ids))
    return tuple(matches)


def apply_copilot(
    decision: Decision,
    threads: tuple[ReviewThread, ...],
    answers: Answers | None,
) -> Decision:
    extra = copilot_matches(threads, answers)
    if not extra:
        return decision
    matched = list(decision.matched_policy_ids)
    disposition = decision.disposition
    policy_id = decision.policy_id
    for match_id, match_disposition in extra:
        if match_id not in matched:
            matched.append(match_id)
        if SEVERITY[match_disposition] > SEVERITY[disposition] or (
            SEVERITY[match_disposition] == SEVERITY[disposition] and policy_id is None
        ):
            disposition = match_disposition
            policy_id = match_id
    return Decision(disposition, policy_id, tuple(matched))