"""In-memory pull requests for workout-app. Not fetched from GitHub."""

from pr_route_workout.facts import CheckStatus
from pr_route_workout.github import PullRequest

FRONTEND_FORM = PullRequest(
    repo="PierreTsia/workout-app",
    number=1,
    url="fixture://frontend-form",
    title="Add new exercise form in workout builder",
    body="T191 Adds a new form for custom exercise creation in the builder.\n\n#191",
    author="ada",
    draft=False,
    head_sha="fixture",
    files=(
        "apps/web/src/components/builder/ExerciseForm.tsx",
        "apps/web/src/components/builder/ExerciseForm.module.css",
    ),
    diff_stat="2 files, +120 -0\napps/web/src/components/builder/ExerciseForm.tsx | +85 -0\napps/web/src/components/builder/ExerciseForm.module.css | +35 -0",
    patch_excerpt=(
        "--- apps/web/src/components/builder/ExerciseForm.tsx\n"
        "+ import { createFormHelper } from '@roma/forms';\n"
        "+ export function ExerciseForm({ onSubmit }: Props) {\n"
        "+   const form = createFormHelper<ExerciseFormData>({ initialValues: {} });\n"
        "+   return <form onSubmit={form.handleSubmit(onSubmit)}>...</form>;\n"
        "+ }\n"
    ),
    checks=CheckStatus.GREEN,
    check_summary="fixture, checks green",
    source="fixture",
)

BACKEND_API = PullRequest(
    repo="PierreTsia/workout-app",
    number=2,
    url="fixture://backend-api",
    title="Add MCP tool for exercise resolution",
    body="New MCP tool resolve_exercises_batch for batch exercise search.\n\n#310",
    author="ada",
    draft=False,
    head_sha="fixture",
    files=(
        "supabase/functions/embedded-agent/tools/resolve_exercises_batch.ts",
        "supabase/functions/embedded-agent/index.ts",
    ),
    diff_stat="2 files, +95 -5\nsupabase/functions/embedded-agent/tools/resolve_exercises_batch.ts | +80 -0\nsupabase/functions/embedded-agent/index.ts | +15 -5",
    patch_excerpt=(
        "--- supabase/functions/embedded-agent/tools/resolve_exercises_batch.ts\n"
        "+ export async function resolveExercisesBatch(input: ResolveBatchInput): Promise<ExerciseResolution[]> {\n"
        "+   // batch resolution logic\n"
        "+ }\n"
    ),
    checks=CheckStatus.GREEN,
    check_summary="fixture, checks green",
    source="fixture",
)

ACHIEVEMENT_TRACK = PullRequest(
    repo="PierreTsia/workout-app",
    number=3,
    url="fixture://achievement-track",
    title="Add new achievement track for consistency",
    body="T220 New badge ladder for workout consistency (streaks, frequency).\n\n#220",
    author="ada",
    draft=False,
    head_sha="fixture",
    files=(
        "supabase/migrations/20240101_add_consistency_achievements.sql",
        "apps/web/src/components/achievements/ConsistencyBadges.tsx",
        "scripts/generate-badge-icons.ts",
    ),
    diff_stat="3 files, +200 -0\nsupabase/migrations/20240101_add_consistency_achievements.sql | +120 -0\napps/web/src/components/achievements/ConsistencyBadges.tsx | +60 -0\nscripts/generate-badge-icons.ts | +20 -0",
    patch_excerpt=(
        "--- supabase/migrations/20240101_add_consistency_achievements.sql\n"
        "+ INSERT INTO achievement_groups (slug, name, description) VALUES ('consistency', 'Consistency', 'Workout streaks');\n"
        "+ INSERT INTO achievement_tiers (group_slug, rank, name, threshold) VALUES ('consistency', 'bronze', 'Starter', 7);\n"
    ),
    checks=CheckStatus.GREEN,
    check_summary="fixture, checks green",
    source="fixture",
)

MCP_TOOL = PullRequest(
    repo="PierreTsia/workout-app",
    number=4,
    url="fixture://mcp-tool",
    title="Add get_user_profile MCP tool",
    body="New MCP tool to fetch user profile for personalized programs.\n\n#231",
    author="ada",
    draft=False,
    head_sha="fixture",
    files=(
        "supabase/functions/embedded-agent/tools/get_user_profile.ts",
        "supabase/functions/embedded-agent/index.ts",
    ),
    diff_stat="2 files, +60 -2\nsupabase/functions/embedded-agent/tools/get_user_profile.ts | +45 -0\nsupabase/functions/embedded-agent/index.ts | +15 -2",
    patch_excerpt=(
        "--- supabase/functions/embedded-agent/tools/get_user_profile.ts\n"
        "+ export async function getUserProfile(userId: string): Promise<UserProfile> {\n"
        "+   const { data } = await supabase.from('user_profiles').select('*').eq('id', userId).single();\n"
        "+   return data;\n"
        "+ }\n"
    ),
    checks=CheckStatus.GREEN,
    check_summary="fixture, checks green",
    source="fixture",
)

DEPENDABOT = PullRequest(
    repo="PierreTsia/workout-app",
    number=5,
    url="fixture://dependabot",
    title="chore(deps): bump @tanstack/react-query from 5.51.0 to 5.52.0",
    body="Updates @tanstack/react-query to 5.52.0.\n\n---\n\nupdated-dependencies:\n- dependency-name: @tanstack/react-query\n  dependency-type: direct:production\n",
    author="dependabot[bot]",
    draft=False,
    head_sha="fixture",
    files=(
        "apps/web/package.json",
        "apps/web/pnpm-lock.yaml",
    ),
    diff_stat="2 files, +5 -5\napps/web/package.json | +1 -1\napps/web/pnpm-lock.yaml | +4 -4",
    patch_excerpt=(
        "--- apps/web/package.json\n"
        "-    \"@tanstack/react-query\": \"^5.51.0\",\n"
        "+    \"@tanstack/react-query\": \"^5.52.0\",\n"
    ),
    checks=CheckStatus.GREEN,
    check_summary="fixture, checks green",
    source="fixture",
)

DOCS_ONLY = PullRequest(
    repo="PierreTsia/workout-app",
    number=6,
    url="fixture://docs-only",
    title="docs: update ADR 0015 with owner_id cloisonnement details",
    body="Adds clarification on application-level owner_id isolation.",
    author="ada",
    draft=False,
    head_sha="fixture",
    files=("docs/adr/0015-application-level-owner-id-isolation.md",),
    diff_stat="1 file, +30 -5\ndocs/adr/0015-application-level-owner-id-isolation.md | +30 -5",
    patch_excerpt=(
        "--- docs/adr/0015-application-level-owner-id-isolation.md\n"
        "+ ## Clarification\n"
        "+ All tables now require explicit owner_id in queries.\n"
    ),
    checks=CheckStatus.GREEN,
    check_summary="fixture, checks green",
    source="fixture",
)

NO_ISSUE = PullRequest(
    repo="PierreTsia/workout-app",
    number=7,
    url="fixture://no-issue",
    title="Refactor exercise search to use new catalog index",
    body="Performance improvement for exercise search using the new catalog index.\n\nNo issue linked - this is a refactor.",
    author="ada",
    draft=False,
    head_sha="fixture",
    files=(
        "apps/web/src/hooks/useExerciseSearch.ts",
        "packages/core/src/exercise-catalog/index.ts",
    ),
    diff_stat="2 files, +40 -15\napps/web/src/hooks/useExerciseSearch.ts | +25 -10\npackages/core/src/exercise-catalog/index.ts | +15 -5",
    patch_excerpt=(
        "--- apps/web/src/hooks/useExerciseSearch.ts\n"
        "- const results = await searchExercisesOld(query);\n"
        "+ const results = await searchExercisesNew(query);\n"
    ),
    checks=CheckStatus.PENDING,
    check_summary="fixture, checks pending",
    source="fixture",
)

FIXTURES = {
    "frontend-form": FRONTEND_FORM,
    "backend-api": BACKEND_API,
    "achievement-track": ACHIEVEMENT_TRACK,
    "mcp-tool": MCP_TOOL,
    "dependabot": DEPENDABOT,
    "docs-only": DOCS_ONLY,
    "no-issue": NO_ISSUE,
}