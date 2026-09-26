"""Facts GitHub can already sign. None of these are Jev questions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath

from pr_route_workout.domains import path_domains

FALSE_PROJECTS = frozenset(
    {"HTTP", "HTTPS", "SHA", "ISO", "UTF", "RFC", "ASCII", "OAUTH", "CVE"}
)
ISSUE_KEY = re.compile(r"(?:#|GH-)(\d+)\b|\b([A-Z][A-Z0-9]+)-(\d+)\b")

BOT_LOGINS = frozenset({"dependabot[bot]", "renovate[bot]"})

FRONTEND_CODE_SUFFIXES = frozenset({".tsx", ".jsx"})
AMBIGUOUS_UI_SUFFIXES = frozenset({".ts", ".js", ".mjs", ".cjs"})
UI_PATH_MARKERS = (
    "/apps/web/src/",
    "/packages/",
    "/components/",
    "/hooks/",
    "/pages/",
    "/ui/",
)

MANIFEST_NAMES = frozenset(
    {
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "pnpm-workspace.yaml",
        "turbo.json",
        "go.mod",
        "go.sum",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "composer.json",
        "composer.lock",
        "uv.lock",
        "cargo.toml",
        "cargo.lock",
        "requirements.txt",
        "poetry.lock",
        "gemfile.lock",
    }
)

DOC_SUFFIXES = frozenset({".md", ".rst", ".adoc", ".mdx"})


class CheckStatus(Enum):
    PENDING = "pending"
    GREEN = "green"
    FAILED = "failed"


@dataclass(frozen=True)
class Facts:
    author_login: str
    author_is_bot: bool
    checks: CheckStatus
    draft: bool
    jira_keys: tuple[str, ...]
    files: tuple[str, ...]
    frontend_code_only: bool
    touches_frontend_code: bool
    dependency_manifest_only: bool
    docs_only: bool
    ui_path: bool
    code_suffixes: tuple[tuple[str, int], ...]
    path_domains: tuple[str, ...]


def issue_keys(
    title: str,
    body: str | None,
    *,
    allow_projects: frozenset[str] | None = None,
) -> tuple[str, ...]:
    """Pull GitHub issue keys out of the title and body.

    Matches `#123`, `GH-123`, and `PROJECT-123` formats.
    With no allowlist, drop known false projects (HTTP-2, SHA-256, etc.).
    """
    seen: list[str] = []
    text = f"{title}\n{body or ''}"
    for match in ISSUE_KEY.finditer(text):
        # Group 1: #123 or GH-123 (just the number)
        # Group 2,3: PROJECT-123 (project, number)
        if match.group(1):
            # #123 or GH-123 format
            key = match.group(1)
        else:
            # PROJECT-123 format
            project, number = match.group(2), match.group(3)
            if allow_projects is not None:
                if project not in allow_projects:
                    continue
            elif project in FALSE_PROJECTS:
                continue
            key = f"{project}-{number}"
        if key not in seen:
            seen.append(key)
    return tuple(seen)


def is_frontend_code(path: str) -> bool:
    lower = path.lower()
    suffix = PurePosixPath(lower).suffix
    if suffix in FRONTEND_CODE_SUFFIXES:
        return True
    if suffix in AMBIGUOUS_UI_SUFFIXES and any(marker in lower for marker in UI_PATH_MARKERS):
        return True
    return False


def is_manifest(path: str) -> bool:
    return PurePosixPath(path.lower()).name in MANIFEST_NAMES


def is_docs(path: str) -> bool:
    lower = path.lower()
    name = PurePosixPath(lower).name
    if name in {"agents.md", "readme.md", "changelog.md", "context.md"}:
        return True
    return PurePosixPath(lower).suffix in DOC_SUFFIXES


def is_ui_path(path: str) -> bool:
    lower = f"/{path.lower()}"
    return any(marker in lower for marker in UI_PATH_MARKERS)


def code_suffix_counts(files: tuple[str, ...] | list[str]) -> tuple[tuple[str, int], ...]:
    counts: dict[str, int] = {}
    for path in files:
        suffix = PurePosixPath(path).suffix.lower() or "(none)"
        counts[suffix] = counts.get(suffix, 0) + 1
    return tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def make_facts(
    *,
    author_login: str,
    checks: CheckStatus,
    draft: bool,
    jira_keys: tuple[str, ...],
    files: tuple[str, ...] | list[str],
) -> Facts:
    paths = tuple(files)
    return Facts(
        author_login=author_login,
        author_is_bot=author_login in BOT_LOGINS,
        checks=checks,
        draft=draft,
        jira_keys=tuple(jira_keys),
        files=paths,
        frontend_code_only=bool(paths) and all(is_frontend_code(path) for path in paths),
        touches_frontend_code=any(is_frontend_code(path) for path in paths),
        dependency_manifest_only=bool(paths) and all(is_manifest(path) for path in paths),
        docs_only=bool(paths) and all(is_docs(path) for path in paths),
        ui_path=any(is_ui_path(path) for path in paths),
        code_suffixes=code_suffix_counts(paths),
        path_domains=path_domains(paths),
    )


FAILED_CONCLUSIONS = frozenset(
    {"failure", "cancelled", "timed_out", "action_required", "stale"}
)


def interpret_checks(
    check_runs: list[dict],
    combined_state: str | None = None,
    *,
    truncated: bool = False,
) -> tuple[CheckStatus, str]:
    if truncated:
        failed = [
            run for run in check_runs if run.get("conclusion") in FAILED_CONCLUSIONS
        ]
        if failed:
            return CheckStatus.FAILED, f"{len(failed)} failed (check list truncated)"
        return CheckStatus.PENDING, "check list truncated"

    if not check_runs:
        if combined_state == "success":
            return CheckStatus.GREEN, "combined status success"
        if combined_state in {"failure", "error"}:
            return CheckStatus.FAILED, f"combined status {combined_state}"
        if combined_state == "pending":
            return CheckStatus.PENDING, "combined status pending"
        return CheckStatus.PENDING, "no check runs"

    failed = [run for run in check_runs if run.get("conclusion") in FAILED_CONCLUSIONS]
    pending = [run for run in check_runs if run.get("status") != "completed"]
    if failed:
        return (
            CheckStatus.FAILED,
            f"{len(failed)} failed of {len(check_runs)} check runs",
        )
    if pending:
        return (
            CheckStatus.PENDING,
            f"{len(pending)} still running of {len(check_runs)} check runs",
        )
    if any(run.get("conclusion") == "success" for run in check_runs):
        return CheckStatus.GREEN, f"{len(check_runs)} check runs succeeded"
    return CheckStatus.PENDING, f"{len(check_runs)} check runs skipped or neutral"