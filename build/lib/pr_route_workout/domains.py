"""workout-app business domains, from docs/CONTEXT.md, ADRs, and epic briefs.

A domain is a business concept. apps/web and apps/api are applications.
"""

from __future__ import annotations

DOMAIN_CRITERIA: dict[str, str] = {
    "programs": (
        "Program lifecycle: programs/, program-generation/, builder/, templates/. "
        "Multi-day training programs, templates, program builder."
    ),
    "exercises": (
        "Exercise catalog: exercises/, exercise-catalog/, exercise-library/. "
        "Exercise definitions, search, resolution, muscle groups."
    ),
    "sessions": (
        "Workout sessions: sessions/, workout/, set-log/, timer/. "
        "Live workout logging, set tracking, rest timers."
    ),
    "achievements": (
        "Gamification: achievements/, badges/, gamification/, badge-icons/. "
        "Achievement groups, tiers, grants, badge icons, unlock overlays."
    ),
    "mcp": (
        "Model Context Protocol: mcp/, embedded-agent/, mcp-tools/. "
        "MCP server, tools, prompts, OAuth, embedded agent threads."
    ),
    "onboarding": (
        "User onboarding: onboarding/, wizard/, recommend-templates/. "
        "Profile creation, template recommendation, first program generation."
    ),
    "library": (
        "Workout library: library/, circuits/, workout-library/. "
        "Saved programs, circuits, browse, add to session."
    ),
    "profile": (
        "User profile: profile/, user-profile/, dashboard/. "
        "Profile dashboard, stats, goals, preferences."
    ),
    "auth": (
        "Authentication: auth/, oauth/, supabase-auth/. "
        "Supabase Auth, OAuth 2.1, consent, API tokens."
    ),
    "infra": (
        "Infrastructure: infra/, database/, migrations/, edge-functions/, ci/. "
        "Supabase migrations, Edge Functions, GitHub Actions, tooling."
    ),
    "docs": (
        "Documentation: docs/, adr/, epic-briefs/, tech-plans/. "
        "ADRs, Epic Briefs, Tech Plans, tickets, CONTEXT.md."
    ),
}

PRIMARY_DOMAIN_INSTRUCTIONS = (
    "Which workout-app business domain is this change mainly about? "
    "Follow the module path. apps/web and apps/api are applications, not domains. "
    "Do not answer with a UI surface: the web app and API are applications. "
    "Program generation logic is programs. Exercise search is exercises. "
    "MCP tools and embedded agent are mcp. Achievement grants are achievements."
)

_MODULES: dict[str, str] = {
    "programs": "programs",
    "program-generation": "programs",
    "builder": "programs",
    "templates": "programs",
    "exercises": "exercises",
    "exercise-catalog": "exercises",
    "exercise-library": "exercises",
    "sessions": "sessions",
    "workout": "sessions",
    "set-log": "sessions",
    "timer": "sessions",
    "achievements": "achievements",
    "badges": "achievements",
    "gamification": "achievements",
    "badge-icons": "achievements",
    "mcp": "mcp",
    "embedded-agent": "mcp",
    "mcp-tools": "mcp",
    "onboarding": "onboarding",
    "wizard": "onboarding",
    "recommend-templates": "onboarding",
    "library": "library",
    "circuits": "library",
    "workout-library": "library",
    "profile": "profile",
    "user-profile": "profile",
    "dashboard": "profile",
    "auth": "auth",
    "oauth": "auth",
    "supabase-auth": "auth",
    "infra": "infra",
    "database": "infra",
    "migrations": "infra",
    "edge-functions": "infra",
    "ci": "infra",
    "docs": "docs",
    "adr": "docs",
    "epic-briefs": "docs",
    "tech-plans": "docs",
    "tickets": "docs",
}

_MODULE_NAMES = tuple(sorted(_MODULES, key=len, reverse=True))


def _match_segment(segment: str) -> str | None:
    for name in _MODULE_NAMES:
        if segment == name or segment.startswith(name + "-"):
            return _MODULES[name]
    return None


def domain_for_path(path: str) -> str | None:
    """First business domain named by a directory. No fallbacks (platform/legacy removed)."""
    for segment in path.lower().split("/"):
        if not segment or segment == ".":
            continue
        domain = _match_segment(segment)
        if domain is not None:
            return domain
    return None


def path_domains(files: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    seen: list[str] = []
    for path in files:
        domain = domain_for_path(path)
        if domain and domain not in seen:
            seen.append(domain)
    return tuple(seen)