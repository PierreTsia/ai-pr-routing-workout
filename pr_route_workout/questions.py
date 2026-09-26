"""One fan-out. Skill Nouls are asked even when the diff is not frontend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pr_route_workout.domains import DOMAIN_CRITERIA, PRIMARY_DOMAIN_INSTRUCTIONS
from pr_route_workout.reviews import ReviewThread, threads_for_fan_out


@dataclass(frozen=True)
class Skill:
    id: str
    instructions: str

    @property
    def question_id(self) -> str:
        return f"skill_{self.id}"


SKILLS: tuple[Skill, ...] = (
    Skill(
        "tdd",
        "The diff adds or changes a test (unit, integration, e2e) or test infrastructure",
    ),
    Skill(
        "microcopy",
        "The diff adds or changes user-visible copy, i18n keys, or translation strings",
    ),
    Skill(
        "epic-brief",
        "The diff creates or updates an Epic Brief, PRD, or ticket breakdown",
    ),
    Skill(
        "tech-plan",
        "The diff creates or updates a Tech Plan, architecture decision, or API design",
    ),
    Skill(
        "new-achievement-track",
        "The diff adds achievement groups, tiers, badge icons, or grant logic",
    ),
    Skill(
        "pr-review",
        "The diff addresses PR review comments or adds review automation",
    ),
    Skill(
        "blog-post",
        "The diff adds or updates a blog post, MDX content, or documentation page",
    ),
    Skill(
        "create-pr",
        "The diff modifies PR templates, release workflows, or branching conventions",
    ),
    Skill(
        "split-tickets",
        "The diff creates implementation tickets from an epic or tech plan",
    ),
    Skill(
        "grill-with-docs",
        "The diff involves domain modeling, ubiquitous language, or ADR updates",
    ),
)

SKILL_NOUL_THRESHOLD = 0.6


@dataclass(frozen=True)
class Question:
    id: str
    kind: str
    instructions: str
    criteria: dict[str, str] | list[str] | None = None
    speculative: bool = False

    def to_api(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": self.kind,
            "instructions": self.instructions,
        }
        if self.criteria is not None:
            payload["criteria"] = self.criteria
        return payload


def question_map(questions: tuple[Question, ...]) -> dict[str, dict[str, Any]]:
    return {question.id: question.to_api() for question in questions}


def _excerpt(text: str, limit: int = 180) -> str:
    return " ".join(text.split())[:limit]


def thread_questions(threads: tuple[ReviewThread, ...]) -> tuple[Question, ...]:
    built: list[Question] = []
    for thread in threads:
        if not thread.tracked:
            continue
        speaker = {"copilot": "Copilot", "claude": "Claude"}.get(thread.source, "Human review")
        excerpt = _excerpt(thread.comments[0].body)
        built.append(
            Question(
                f"thread_{thread.id}_addressed",
                "noul",
                (
                    f"{speaker} thread {thread.id} on {thread.path} is addressed by a later commit "
                    f"or reply, not merely acknowledged. Comment: {excerpt}"
                ),
                speculative=True,
            )
        )
        built.append(
            Question(
                f"thread_{thread.id}_stance",
                "choice",
                f"What is the state of this {speaker} thread {thread.id} on {thread.path}? Comment: {excerpt}",
                {
                    "unanswered": "No later change or reply deals with the comment",
                    "acknowledged": "Someone replied, but the requested code change is not evident",
                    "addressed": "A later commit or reply shows the comment was handled",
                    "disputed": "The author explains why the comment should not be applied",
                },
                speculative=True,
            )
        )
    return tuple(built)


def build_questions(threads: tuple[ReviewThread, ...] = ()) -> tuple[Question, ...]:
    core = (
        Question(
            "change_shape",
            "choice",
            "What kind of change is this pull request?",
            {
                "dependency_bump": "A dependency bump, lockfile included, with no intended product change",
                "mechanical_chore": "Formatting, rename, generated code, or config that does not change marketplace behavior",
                "bugfix": "Restores behavior that already existed and regressed",
                "feature": "New or changed product behavior",
                "migration": "Moves or rewrites stored data, or a schema operators cannot roll back casually",
                "revert": "Undoes a previous change",
            },
        ),
        Question(
            "primary_domain",
            "choice",
            PRIMARY_DOMAIN_INSTRUCTIONS,
            DOMAIN_CRITERIA,
        ),
        Question(
            "main_code",
            "choice",
            (
                "Which source type is most of the changed files? "
                "Use the file names. A title about a UI page does not make a .py diff into .tsx."
            ),
            {
                "tsx": "Most changed files are .tsx",
                "ts": "Most changed files are .ts",
                "py": "Most changed files are .py",
                "sql": "Most changed files are .sql",
                "yaml": "Most changed files are .yaml/.yml",
                "md": "Most changed files are .md/.mdx",
                "other": "Another type, or no single source type is most of the diff",
            },
        ),
        Question(
            "changes_runtime",
            "noul",
            "The diff changes product behavior at runtime, beyond a lockfile or version bump",
        ),
        Question(
            "review_depth",
            "score",
            "How deep a review does this diff require?",
            [
                "Lockfile, formatting, or a generated file, with no behavior to review",
                "One local behavior change a teammate can check in the diff",
                "A domain rule in programs, exercises, sessions, achievements, or mcp",
                "A public API, MCP tool contract, or a data migration",
            ],
        ),
        Question(
            "blast_radius",
            "score",
            "How far does this change reach?",
            [
                "A single file, or a bump that does not reach runtime",
                "One module inside a single domain",
                "More than one workout-app business domain in the same change",
                "A public API or a marketplace-wide contract",
            ],
        ),
    )
    skills = tuple(
        Question(skill.question_id, "noul", skill.instructions, speculative=True)
        for skill in SKILLS
    )
    return core + skills + thread_questions(threads_for_fan_out(threads))