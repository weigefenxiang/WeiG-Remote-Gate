from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
ROUTINE_WORKFLOW = ROOT / ".github" / "workflows" / "v030-ci.yml"
RELEASE_BROWSER_WORKFLOW = ROOT / ".github" / "workflows" / "browser-release.yml"


class CiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.routine_workflow = ROUTINE_WORKFLOW.read_text(encoding="utf-8")
        cls.release_browser_workflow = RELEASE_BROWSER_WORKFLOW.read_text(encoding="utf-8")

    def test_push_ci_uses_single_fixed_dev_branch(self):
        self.assertIn("push:\n    branches:\n      - dev", self.routine_workflow)
        self.assertNotIn("dev/v0.3.*", self.routine_workflow)

    def test_routine_ci_does_not_run_browser_matrix(self):
        self.assertNotIn("browser:", self.routine_workflow)
        self.assertNotIn("playwright install", self.routine_workflow)
        self.assertNotIn("node tests/browser_layout.mjs", self.routine_workflow)
        self.assertNotIn("node tests/browser_split_dual.mjs", self.routine_workflow)

    def test_release_browser_validation_is_main_only_and_manual(self):
        self.assertIn("workflow_dispatch:", self.release_browser_workflow)
        self.assertIn("if: github.ref == 'refs/heads/main'", self.release_browser_workflow)
        self.assertIn("- name: Linux browser matrix", self.release_browser_workflow)
        self.assertIn("- name: Windows browser matrix", self.release_browser_workflow)
        self.assertNotIn("push:", self.release_browser_workflow)
        self.assertNotIn("pull_request:", self.release_browser_workflow)

    def test_release_browser_validation_installs_playwright_without_apt_dependencies(self):
        self.assertIn("npm install --no-save playwright@1.55.0", self.release_browser_workflow)
        self.assertIn("npx playwright install chromium", self.release_browser_workflow)
        self.assertNotIn("playwright install --with-deps", self.release_browser_workflow)
        self.assertIn("node tests/browser_layout.mjs", self.release_browser_workflow)
        self.assertIn("node tests/browser_split_dual.mjs", self.release_browser_workflow)

    def test_browser_workflows_do_not_use_ubuntu_package_installers(self):
        workflows = self.routine_workflow + "\n" + self.release_browser_workflow
        self.assertNotIn("apt-get install", workflows)
        self.assertNotIn("apt install", workflows)
        self.assertNotIn("azure.archive.ubuntu.com", workflows)
        self.assertNotIn("chromium-browser", workflows)


if __name__ == "__main__":
    unittest.main()
