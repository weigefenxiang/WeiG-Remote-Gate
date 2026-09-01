from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "sdk-compat.yml").read_text(encoding="utf-8")


class SdkWorkflowTriggerTests(unittest.TestCase):
    def test_sdk_compat_runs_on_relevant_dev_changes_only(self):
        self.assertIn("push:", WORKFLOW)
        self.assertIn("- dev", WORKFLOW)
        for path in (
            "VERSION",
            "native/remote-gate-mapper.c",
            "native/remote-gate-mapper-entry.c",
            "native/build-openwrt-sdk.sh",
            "native/run-sdk-compat.sh",
            "native/mapper-abi-map.tsv",
            "native/mapper-build-classes.tsv",
            "native/sdk-compat-matrix.tsv",
            "native/openwrt-sdk-package/**",
        ):
            self.assertIn(path, WORKFLOW)
        self.assertNotIn("server/**", WORKFLOW)
        self.assertNotIn("openwrt/**", WORKFLOW)

    def test_representative_family_matrix_is_kept(self):
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
