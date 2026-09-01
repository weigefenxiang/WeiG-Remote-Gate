from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "v030-ci.yml"


class CiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_push_ci_uses_single_fixed_dev_branch(self):
        self.assertIn("push:\n    branches:\n      - dev", self.workflow)
        self.assertNotIn("dev/v0.3.*", self.workflow)

    def test_browser_job_waits_for_core(self):
        self.assertIn("browser:\n    runs-on: ubuntu-latest\n    needs: core", self.workflow)

    def test_browser_job_installs_playwright_runtime(self):
        self.assertIn("npm install --no-save playwright@1.55.0", self.workflow)
        self.assertIn("npx playwright install --with-deps chromium", self.workflow)
        self.assertIn("node tests/browser_layout.mjs", self.workflow)

    def test_browser_job_does_not_use_ubuntu_chromium_snap_stub(self):
        self.assertNotIn("apt-get install -y chromium-browser", self.workflow)


if __name__ == "__main__":
    unittest.main()
