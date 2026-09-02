from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
ROUTINE_WORKFLOW = ROOT / ".github" / "workflows" / "v030-ci.yml"
RELEASE_BROWSER_WORKFLOW = ROOT / ".github" / "workflows" / "browser-release.yml"
CANDIDATE_BROWSER_WORKFLOW = ROOT / ".github" / "workflows" / "browser-dev-candidate.yml"
BROWSER_MATRIX_WORKFLOW = ROOT / ".github" / "workflows" / "browser-matrix.yml"


class CiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.routine_workflow = ROUTINE_WORKFLOW.read_text(encoding="utf-8")
        cls.release_browser_workflow = RELEASE_BROWSER_WORKFLOW.read_text(encoding="utf-8")
        cls.candidate_browser_workflow = CANDIDATE_BROWSER_WORKFLOW.read_text(encoding="utf-8")
        cls.browser_matrix_workflow = BROWSER_MATRIX_WORKFLOW.read_text(encoding="utf-8")

    def test_push_ci_uses_single_fixed_dev_branch(self):
        self.assertIn("push:\n    branches:\n      - dev", self.routine_workflow)
        self.assertNotIn("dev/v0.3.*", self.routine_workflow)

    def test_routine_ci_does_not_run_browser_matrix(self):
        self.assertNotIn("playwright install", self.routine_workflow)
        self.assertNotIn("node tests/browser_layout.mjs", self.routine_workflow)
        self.assertNotIn("node tests/browser_split_dual.mjs", self.routine_workflow)

    def test_release_browser_validation_remains_main_only_and_manual(self):
        self.assertIn("workflow_dispatch:", self.release_browser_workflow)
        self.assertIn("if: github.ref == 'refs/heads/main'", self.release_browser_workflow)
        self.assertIn("uses: ./.github/workflows/browser-matrix.yml", self.release_browser_workflow)
        self.assertNotIn("push:", self.release_browser_workflow)
        self.assertNotIn("pull_request:", self.release_browser_workflow)

    def test_dev_candidate_matrix_is_explicit_and_does_not_change_routine_ci(self):
        self.assertIn("push:\n    branches:\n      - dev", self.candidate_browser_workflow)
        self.assertIn("contains(github.event.head_commit.message, '[browser-matrix]')", self.candidate_browser_workflow)
        self.assertIn("uses: ./.github/workflows/browser-matrix.yml", self.candidate_browser_workflow)
        self.assertNotIn("workflow_dispatch:", self.candidate_browser_workflow)

    def test_shared_browser_matrix_is_exact_cross_platform_playwright_validation(self):
        workflow = self.browser_matrix_workflow
        self.assertIn("workflow_call:", workflow)
        self.assertIn("- name: Linux browser matrix", workflow)
        self.assertIn("- name: Windows browser matrix", workflow)
        self.assertIn('test "$actual" = "$GITHUB_SHA"', workflow)
        self.assertIn("npm install --no-save playwright@1.55.0", workflow)
        self.assertIn("npx playwright install chromium", workflow)
        self.assertNotIn("playwright install --with-deps", workflow)
        for script in (
            "browser_layout.mjs",
            "browser_access_pathcard.mjs",
            "browser_split_dual.mjs",
            "browser_plan_preferences.mjs",
            "browser_plan_service_identity.mjs",
            "browser_gate_profile_binding.mjs",
            "browser_egress_manual.mjs",
            "browser_mixed_egress.mjs",
        ):
            self.assertIn(f"node tests/{script}", workflow)

    def test_browser_workflows_do_not_use_ubuntu_package_installers(self):
        workflows = "\n".join((
            self.routine_workflow,
            self.release_browser_workflow,
            self.candidate_browser_workflow,
            self.browser_matrix_workflow,
        ))
        self.assertNotIn("apt-get install", workflows)
        self.assertNotIn("apt install", workflows)
        self.assertNotIn("azure.archive.ubuntu.com", workflows)
        self.assertNotIn("chromium-browser", workflows)


if __name__ == "__main__":
    unittest.main()
