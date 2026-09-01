from pathlib import Path
import os
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "openwrt" / "remote-gate-platform.sh"
INSTALL = (ROOT / "openwrt" / "install.sh").read_text(encoding="utf-8")
UPDATE = (ROOT / "openwrt" / "update.sh").read_text(encoding="utf-8")
AUDIT = (ROOT / "openwrt" / "remote-gate-audit.sh").read_text(encoding="utf-8")
INIT = (ROOT / "openwrt" / "remote-gate-agent.init").read_text(encoding="utf-8")
RULES = (ROOT / "docs" / "PROJECT-RULES.md").read_text(encoding="utf-8")


class PlatformCompatibilityTests(unittest.TestCase):
    def run_platform(self, action, release_text="", fake_commands=None, root_setup=None, with_procd=True):
        fake_commands = fake_commands or {}
        with tempfile.TemporaryDirectory() as td:
            temp = Path(td)
            release = temp / "openwrt_release"
            release.write_text(release_text, encoding="utf-8")
            os_release = temp / "missing-os-release"
            rc_common = temp / "rc.common"
            rc_common.write_text("#!/bin/sh\n", encoding="utf-8")
            procd = temp / ("procd" if with_procd else "missing-procd")
            if with_procd:
                procd.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                procd.chmod(0o755)

            fake_bin = temp / "bin"
            fake_bin.mkdir()
            for name, body in fake_commands.items():
                path = fake_bin / name
                path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
                path.chmod(0o755)

            root = temp / "root"
            root.mkdir()
            if root_setup:
                root_setup(root)

            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{fake_bin}{os.pathsep}{env.get('PATH', '')}",
                    "REMOTE_GATE_OPENWRT_RELEASE_FILE": str(release),
                    "REMOTE_GATE_OS_RELEASE_FILE": str(os_release),
                    "REMOTE_GATE_RC_COMMON_FILE": str(rc_common),
                    "REMOTE_GATE_PROCD_FILE": str(procd),
                    "REMOTE_GATE_ROOT_PREFIX": str(root),
                }
            )
            return subprocess.run(
                ["sh", str(PLATFORM), action],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

    def test_lede_release_metadata_is_accepted_without_version_gate(self):
        release = """\
DISTRIB_ID='LEDE'
DISTRIB_RELEASE='17.01.7'
DISTRIB_TARGET='ar71xx/generic'
DISTRIB_ARCH='mips_24kc'
"""
        self.assertEqual(self.run_platform("distribution", release).stdout.strip(), "LEDE")
        self.assertEqual(self.run_platform("release", release).stdout.strip(), "17.01.7")
        self.assertEqual(self.run_platform("package-arch", release).stdout.strip(), "mips_24kc")

    def test_immortalwrt_release_metadata_uses_same_contract(self):
        release = """\
DISTRIB_ID='ImmortalWrt'
DISTRIB_RELEASE='24.10'
DISTRIB_TARGET='mediatek/filogic'
DISTRIB_ARCH='aarch64_cortex-a53'
"""
        result = self.run_platform("summary", release)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Distribution: ImmortalWrt", result.stdout)
        self.assertIn("Package ABI: aarch64_cortex-a53", result.stdout)

    def test_apk_arch_is_supported_for_new_openwrt(self):
        release = """\
DISTRIB_ID='OpenWrt'
DISTRIB_RELEASE='25.12'
DISTRIB_TARGET='mediatek/filogic'
"""
        apk = {
            "apk": """
                #!/bin/sh
                [ "${1:-}" = "--print-arch" ] && { echo aarch64_cortex-a53; exit 0; }
                exit 1
            """
        }
        self.assertEqual(self.run_platform("package-manager", release, apk).stdout.strip(), "apk")
        self.assertEqual(self.run_platform("package-arch", release, apk).stdout.strip(), "aarch64_cortex-a53")

    def test_opkg_uses_highest_priority_real_arch(self):
        release = """\
DISTRIB_ID='OpenWrt'
DISTRIB_RELEASE='21.02.7'
DISTRIB_TARGET='ramips/mt7621'
"""
        opkg = {
            "opkg": """
                #!/bin/sh
                [ "${1:-}" = "print-architecture" ] || exit 1
                echo 'arch all 1'
                echo 'arch noarch 1'
                echo 'arch mipsel_24kc 10'
                echo 'arch mipsel_24kc_24kf 20'
            """
        }
        self.assertEqual(self.run_platform("package-manager", release, opkg).stdout.strip(), "opkg")
        self.assertEqual(self.run_platform("package-arch", release, opkg).stdout.strip(), "mipsel_24kc_24kf")

    def test_apk_is_preferred_when_both_package_managers_exist(self):
        commands = {
            "apk": "#!/bin/sh\necho x86_64\n",
            "opkg": "#!/bin/sh\necho 'arch x86_64 10'\n",
        }
        self.assertEqual(self.run_platform("package-manager", fake_commands=commands).stdout.strip(), "apk")

    def test_mapper_abi_never_falls_back_to_uname(self):
        result = self.run_platform(
            "package-arch",
            "DISTRIB_ID='OpenWrt'\nDISTRIB_RELEASE='custom'\n",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")

    def test_libc_family_supports_old_and_new_userspaces(self):
        cases = {
            "musl": "lib/ld-musl-mipsel.so.1",
            "uclibc": "lib/ld-uClibc.so.0",
            "glibc": "lib/ld-linux.so.2",
        }
        for expected, relative in cases.items():
            with self.subTest(expected=expected):
                def setup(root, relative=relative):
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("", encoding="utf-8")

                result = self.run_platform("libc", root_setup=setup)
                self.assertEqual(result.stdout.strip(), expected)

    def test_rc_common_without_procd_is_a_supported_service_framework(self):
        result = self.run_platform("init", with_procd=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "rc.common")
        self.assertIn("procd|rc.common", INSTALL)
        self.assertIn("procd|rc.common", UPDATE)
        self.assertNotIn("currently requires OpenWrt procd", INSTALL)
        self.assertNotIn("currently requires OpenWrt procd", UPDATE)

    def test_legacy_init_fallback_checks_pid_ownership(self):
        self.assertIn("USE_PROCD=1", INIT)
        self.assertIn("pid_owned()", INIT)
        self.assertIn("/proc/$pid/cmdline", INIT)
        self.assertIn("legacy_start_one()", INIT)
        self.assertIn("legacy_stop_one()", INIT)
        self.assertIn("return-route-loop", INIT)

    def test_agent_control_polling_defaults_to_five_seconds(self):
        self.assertIn('AGENT_INTERVAL="${REMOTE_GATE_AGENT_INTERVAL:-5}"', INIT)
        self.assertIn('procd_set_param env AGENT_INTERVAL="$AGENT_INTERVAL"', INIT)
        self.assertIn("export AGENT_INTERVAL", INIT)

    def test_lifecycle_deploys_shared_platform_helper(self):
        self.assertIn('fetch_file "remote-gate-platform.sh"', INSTALL)
        self.assertIn('FILES="remote-gate-platform.sh ', UPDATE)
        self.assertIn('remote-gate-platform.sh remote-gate-report.sh', UPDATE)
        self.assertIn('"$PLATFORM" core-capable', INSTALL)
        self.assertIn('remote-gate-platform.sh" core-capable', UPDATE)

    def test_audit_supports_both_package_manager_generations(self):
        self.assertIn("if has apk", AUDIT)
        self.assertIn("apk --print-arch", AUDIT)
        self.assertIn("apk list -I", AUDIT)
        self.assertIn("elif has opkg", AUDIT)
        self.assertIn("opkg print-architecture", AUDIT)

    def test_hard_rules_are_capability_based_not_release_allowlist(self):
        self.assertIn("OpenWrt, LEDE, ImmortalWrt", RULES)
        self.assertIn("capability detection", RULES)
        self.assertIn("`apk`", RULES)
        self.assertIn("`opkg`", RULES)
        self.assertIn("must not be treated as sufficient authority", RULES)


if __name__ == "__main__":
    unittest.main()
