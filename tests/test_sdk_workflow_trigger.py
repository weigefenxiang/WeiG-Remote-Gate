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
            "openwrt-19.07.0-x86_64",
            "openwrt-19.07.9-armvirt-64",
            "openwrt-19.07.9-x86_64",
            "openwrt-19.07.10-x86_64",
            "openwrt-19.07.10-x86-geode",
            "openwrt-19.07.10-ramips-mt76x8",
            "openwrt-19.07.10-ar71xx-generic",
            "openwrt-21.02.7-x86_64",
            "openwrt-24.10.5-x86_64",
            "openwrt-25.12.5-x86_64",
            "immortalwrt-24.10.5-x86_64",
        ):
            self.assertIn(sample, WORKFLOW)

    def test_manual_dispatch_can_target_one_sdk_sample(self):
        self.assertIn("inputs:", WORKFLOW)
        self.assertIn("description: SDK sample to validate", WORKFLOW)
        self.assertIn("default: all", WORKFLOW)
        self.assertIn("type: choice", WORKFLOW)
        self.assertIn("fromJSON(inputs.sample == 'all'", WORKFLOW)
        self.assertIn("format('[\"{0}\"]', inputs.sample)", WORKFLOW)

    def test_openwrt_1907_uses_current_runner_after_modern_host_verification(self):
        self.assertIn("runs-on: ubuntu-latest", WORKFLOW)
        self.assertNotIn("ubuntu-22.04", WORKFLOW)
        self.assertNotIn("matrix.sample == 'openwrt-19.07.10-x86_64' &&", WORKFLOW)
        self.assertIn("qemu-user", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
