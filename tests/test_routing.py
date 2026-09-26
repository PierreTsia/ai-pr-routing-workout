"""Tests for pr-route-workout."""

import unittest
from pr_route_workout.facts import (
    CheckStatus,
    interpret_checks,
    is_frontend_code,
    is_manifest,
    is_docs,
    issue_keys,
    make_facts,
)
from pr_route_workout.domains import domain_for_path, path_domains
from pr_route_workout.policies import route, Disposition
from pr_route_workout.run import evaluate
from pr_route_workout.fixtures import FIXTURES


class TestFacts(unittest.TestCase):
    def test_is_frontend_code(self):
        self.assertTrue(is_frontend_code("apps/web/src/components/Button.tsx"))
        self.assertTrue(is_frontend_code("packages/core/src/hooks/useSomething.ts"))
        self.assertFalse(is_frontend_code("apps/api/src/routes/health.ts"))
        self.assertFalse(is_frontend_code("supabase/functions/embedded-agent/index.ts"))

    def test_is_manifest(self):
        self.assertTrue(is_manifest("pnpm-lock.yaml"))
        self.assertTrue(is_manifest("package.json"))
        self.assertTrue(is_manifest("turbo.json"))
        self.assertFalse(is_manifest("apps/web/src/main.tsx"))

    def test_is_docs(self):
        self.assertTrue(is_docs("docs/adr/0001.md"))
        self.assertTrue(is_docs("README.md"))
        self.assertTrue(is_docs("CHANGELOG.md"))
        self.assertTrue(is_docs("CONTEXT.md"))
        self.assertFalse(is_docs("apps/web/src/App.tsx"))

    def test_issue_keys(self):
        keys = issue_keys("Fix bug #123", "Related to GH-456")
        self.assertEqual(keys, ("123", "456"))

    def test_issue_keys_false_projects(self):
        keys = issue_keys("HTTP-2 is not a ticket", "SHA-256 hash")
        self.assertEqual(keys, ())

    def test_interpret_checks_green(self):
        runs = [{"conclusion": "success", "status": "completed"}]
        status, _ = interpret_checks(runs)
        self.assertEqual(status, CheckStatus.GREEN)

    def test_interpret_checks_failed(self):
        runs = [{"conclusion": "failure", "status": "completed"}]
        status, _ = interpret_checks(runs)
        self.assertEqual(status, CheckStatus.FAILED)

    def test_interpret_checks_pending(self):
        runs = [{"conclusion": None, "status": "in_progress"}]
        status, _ = interpret_checks(runs)
        self.assertEqual(status, CheckStatus.PENDING)


class TestDomains(unittest.TestCase):
    def test_domain_for_path(self):
        self.assertEqual(domain_for_path("apps/web/src/components/builder/ExerciseForm.tsx"), "programs")
        self.assertEqual(domain_for_path("supabase/functions/embedded-agent/index.ts"), "mcp")
        self.assertEqual(domain_for_path("supabase/migrations/001.sql"), "infra")
        self.assertEqual(domain_for_path("docs/adr/0015.md"), "docs")
        self.assertIsNone(domain_for_path("random/path/file.txt"))

    def test_path_domains(self):
        files = [
            "apps/web/src/components/builder/ExerciseForm.tsx",
            "packages/core/src/exercise-catalog/search.ts",
        ]
        domains = path_domains(files)
        self.assertEqual(domains, ("programs", "exercises"))


class TestFixtures(unittest.TestCase):
    def test_frontend_form_fixture(self):
        pr = FIXTURES["frontend-form"]
        result = evaluate(pr)
        # Frontend form should match tdd_job or microcopy_job or epic_brief_job
        # At minimum, it should not be blocked
        self.assertNotEqual(result.decision.disposition, Disposition.BLOCKED)
        # The fixture has frontend files, so it should touch frontend code
        self.assertTrue(any("apps/web" in f for f in pr.files))

    def test_dependabot_fixture(self):
        pr = FIXTURES["dependabot"]
        result = evaluate(pr)
        self.assertEqual(result.decision.disposition, Disposition.READY_FOR_MERGE)

    def test_no_issue_fixture(self):
        pr = FIXTURES["no-issue"]
        result = evaluate(pr)
        # No issue key, not manifest, not docs -> needs_author
        self.assertEqual(result.decision.disposition, Disposition.NEEDS_AUTHOR)

    def test_docs_only_fixture(self):
        pr = FIXTURES["docs-only"]
        result = evaluate(pr)
        # Docs only -> ready_for_hitl (no issue key but docs_only is true)
        self.assertNotEqual(result.decision.disposition, Disposition.NEEDS_AUTHOR)

    def test_achievement_track_fixture(self):
        pr = FIXTURES["achievement-track"]
        result = evaluate(pr)
        self.assertNotEqual(result.decision.disposition, Disposition.BLOCKED)


class TestPolicies(unittest.TestCase):
    def test_failing_checks_blocked(self):
        from pr_route_workout.facts import make_facts, CheckStatus
        facts = make_facts(
            author_login="ada",
            checks=CheckStatus.FAILED,
            draft=False,
            jira_keys=(),
            files=("apps/web/src/App.tsx",),
        )
        decision = route(facts, None)
        self.assertEqual(decision.disposition, Disposition.BLOCKED)

    def test_bot_manifest_green(self):
        from pr_route_workout.facts import make_facts, CheckStatus
        facts = make_facts(
            author_login="dependabot[bot]",
            checks=CheckStatus.GREEN,
            draft=False,
            jira_keys=(),
            files=("pnpm-lock.yaml",),
        )
        decision = route(facts, None)
        self.assertEqual(decision.disposition, Disposition.READY_FOR_MERGE)


if __name__ == "__main__":
    unittest.main()