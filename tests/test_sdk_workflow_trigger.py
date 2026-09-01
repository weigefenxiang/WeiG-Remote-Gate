from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "sdk-compat.yml").read_text(encoding="utf-8")


class SdkWorkflowTriggerTests(unittest.TestCase):
    def test_sdk_compat_is_manual_only_while_current_device_is_priority(self):
        self.assertIn("workflow_dispatch:", WORKFLOW)
        self.assertNotIn("push:", WORKFLOW)
        self.assertNotIn("schedule:", WORKFLOW)

    def test_representative_family_matrix_is_kept_for_later_manual_validation(self):
        for sample in (
            "openwrt-19.07.10-x86_64",
            "openwrt-21.02.7-x86_64",
            "openwrt-24.10.5-x86_64",
            "openwrt-25.12.5-x86_64",
            "immortalwrt-24.10.5-x86_64",
        ):
            self.assertIn(sample, WORKFLOW)


if __name__ == "__main__":
    unittest.main()
