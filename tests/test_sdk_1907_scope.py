from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = (ROOT / "native" / "run-sdk-compat.sh").read_text(encoding="utf-8")
BUILDER = (ROOT / "native" / "build-openwrt-sdk.sh").read_text(encoding="utf-8")


class OpenWrt1907ScopeTests(unittest.TestCase):
    def test_compiler_prerequisite_compatibility_is_1907_only(self):
        self.assertIn("sdk_allow_compiler_prereq=0", RUNNER)
        self.assertIn("openwrt-19.07.*-*)", RUNNER)
        self.assertEqual(RUNNER.count("sdk_allow_compiler_prereq=1"), 1)
        self.assertIn(
            'REMOTE_GATE_SDK_ALLOW_COMPILER_PREREQ="$sdk_allow_compiler_prereq"',
            RUNNER,
        )
        self.assertNotIn("openwrt-21.*-*) sdk_allow_compiler_prereq=1", RUNNER)
        self.assertNotIn("immortalwrt-*) sdk_allow_compiler_prereq=1", RUNNER)

    def test_builder_keeps_compiler_false_negative_path_fail_closed(self):
        self.assertIn(
            'SDK_ALLOW_COMPILER_PREREQ="${REMOTE_GATE_SDK_ALLOW_COMPILER_PREREQ:-0}"',
            BUILDER,
        )
        self.assertIn('case "$SDK_ALLOW_COMPILER_PREREQ" in 0|1)', BUILDER)
        self.assertIn("validate_host_compiler", BUILDER)
        self.assertIn("host_compiler_version_ok", BUILDER)
        self.assertIn("gcc prerequisite failed outside validated compiler compatibility mode", BUILDER)
        self.assertIn("g++ prerequisite failed outside validated compiler compatibility mode", BUILDER)
        self.assertIn("prerequisite failures exceed validated legacy host exceptions", BUILDER)

    def test_x86_64_build_id_scope_remains_separate_from_compiler_compatibility(self):
        self.assertIn(
            "openwrt-19.07.*-x86_64) sdk_link_flags='-Wl,--build-id=sha1'",
            RUNNER,
        )
        self.assertEqual(RUNNER.count("sdk_link_flags='-Wl,--build-id=sha1'"), 1)
        self.assertIn("openwrt-19.07.10-x86-geode) sdk_emulator='qemu-i386'", RUNNER)
        self.assertIn("openwrt-19.07.9-armvirt-64) sdk_emulator='qemu-aarch64'", RUNNER)


if __name__ == "__main__":
    unittest.main()
