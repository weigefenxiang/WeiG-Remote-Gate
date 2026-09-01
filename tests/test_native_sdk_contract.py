from pathlib import Path
import os
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native"
BUILD_SDK = NATIVE / "build-openwrt-sdk.sh"
ABI_MAP = NATIVE / "mapper-abi-map.tsv"
CLASSES = NATIVE / "mapper-build-classes.tsv"


def parse_tsv(path: Path, columns: int):
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.startswith("#"):
            continue
        parts = raw.split("\t")
        if len(parts) != columns:
            raise AssertionError(f"{path}: expected {columns} columns: {raw}")
        rows.append(parts)
    return rows


class NativeSdkContractTests(unittest.TestCase):
    def test_abi_delivery_matches_build_class_validation(self):
        classes = {row[0]: row for row in parse_tsv(CLASSES, 4)}
        self.assertTrue(classes)
        for abi, build_class, delivery in parse_tsv(ABI_MAP, 3):
            self.assertIn(build_class, classes, abi)
            validation = classes[build_class][3]
            if delivery == "cross-candidate":
                self.assertEqual(validation, "cross-build", abi)
            elif delivery == "sdk-required":
                self.assertEqual(validation, "openwrt-sdk-required", abi)
            else:
                self.fail(f"unknown delivery status for {abi}: {delivery}")

    def _fake_environment(self, sdk: Path, expected_abi: str):
        fakebin = sdk.parent / "fakebin"
        fakebin.mkdir()
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

        make = fakebin / "make"
        make.write_text(
            "#!/bin/sh\n"
            "case \" $* \" in\n"
            "  *' prereq '*)\n"
            "    if [ \"${REQUIRE_TOPDIR_ARG:-0}\" = 1 ]; then\n"
            "      case \" $* \" in *\" TOPDIR=$PWD/ \"*) ;; *) echo 'missing TOPDIR make argument' >&2; exit 10 ;; esac\n"
            "    fi\n"
            "    case \"${FAKE_PREREQ_FAILURE:-none}\" in\n"
            "      python2)\n"
            "        echo \"Checking 'python'... failed.\"\n"
            "        echo\n"
            "        echo 'Build dependency: Please install Python 2.x'\n"
            "        exit 2\n"
            "        ;;\n"
            "      other)\n"
            "        echo \"Checking 'tar'... failed.\"\n"
            "        echo\n"
            "        echo \"Build dependency: Please install GNU 'tar'\"\n"
            "        exit 2\n"
            "        ;;\n"
            "      none) exit 0 ;;\n"
            "      *) echo 'invalid fake prerequisite mode' >&2; exit 8 ;;\n"
            "    esac\n"
            "    ;;\n"
            "esac\n"
            "if [ \"${REQUIRE_PREREQ_STAMP:-0}\" = 1 ] && [ ! -f \"$PWD/staging_dir/host/.prereq-build\" ]; then\n"
            "  echo 'missing validated prerequisite stamp' >&2\n"
            "  exit 9\n"
            "fi\n"
            "case \" $* \" in\n"
            "  *' package/weig-remote-gate-mapper/compile '*)\n"
            "    if [ \"${REQUIRE_BUILD_ID_FLAG:-0}\" = 1 ] && [ \"${REMOTE_GATE_SDK_LINK_FLAGS:-}\" != '-Wl,--build-id=sha1' ]; then\n"
            "      echo 'missing validated build-id link flag' >&2\n"
            "      exit 11\n"
            "    fi\n"
            f"    out=\"$PWD/build_dir/target-test/remote-gate-mapper-{version}/remote-gate-mapper\"\n"
            "    mkdir -p \"$(dirname \"$out\")\"\n"
            "    printf '#!/bin/sh\\nexit 0\\n' > \"$out\"\n"
            "    chmod 0755 \"$out\"\n"
            "    ;;\n"
            "esac\n"
            "exit 0\n",
            encoding="utf-8",
        )
        make.chmod(0o755)

        file_cmd = fakebin / "file"
        file_cmd.write_text(
            "#!/bin/sh\n"
            "printf '%s: ELF test executable, statically linked\\n' \"$1\"\n",
            encoding="utf-8",
        )
        file_cmd.chmod(0o755)

        sdk.mkdir()
        (sdk / "rules.mk").write_text("# fake OpenWrt-family SDK\n", encoding="utf-8")
        (sdk / "include").mkdir()
        (sdk / "include" / "prereq-build.mk").write_text("# fake prerequisite target\n", encoding="utf-8")
        (sdk / ".config").write_text(
            f'CONFIG_TARGET_ARCH_PACKAGES="{expected_abi}"\n', encoding="utf-8"
        )
        env = os.environ.copy()
        env["PATH"] = f"{fakebin}:{env['PATH']}"
        return env

    def test_sdk_builder_exports_exact_abi_binary(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sdk = base / "sdk"
            out = base / "out"
            env = self._fake_environment(sdk, "powerpc64_e5500")
            result = subprocess.run(
                ["sh", str(BUILD_SDK), str(sdk), "powerpc64_e5500", str(out)],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((out / "remote-gate-mapper-powerpc64_e5500").is_file())
            self.assertIn("delivery=sdk-required", result.stdout)
            self.assertIn("validation=openwrt-sdk-required", result.stdout)
            self.assertFalse((sdk / "package" / "weig-remote-gate-mapper").exists())

    def test_sdk_builder_rejects_abi_mismatch_before_build(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sdk = base / "sdk"
            env = self._fake_environment(sdk, "mips_24kc")
            result = subprocess.run(
                ["sh", str(BUILD_SDK), str(sdk), "powerpc64_e5500", str(base / "out")],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SDK ABI mismatch", result.stderr)
            self.assertFalse((sdk / "build_dir").exists())

    def test_legacy_python2_only_failure_gets_validated_prerequisite_stamp(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sdk = base / "sdk"
            out = base / "out"
            env = self._fake_environment(sdk, "powerpc64_e5500")
            env["REMOTE_GATE_SDK_FORCE_PREREQ"] = "1"
            env["REMOTE_GATE_SDK_LINK_FLAGS"] = "-Wl,--build-id=sha1"
            env["FAKE_PREREQ_FAILURE"] = "python2"
            env["REQUIRE_PREREQ_STAMP"] = "1"
            env["REQUIRE_TOPDIR_ARG"] = "1"
            env["REQUIRE_BUILD_ID_FLAG"] = "1"
            result = subprocess.run(
                ["sh", str(BUILD_SDK), str(sdk), "powerpc64_e5500", str(out)],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((out / "remote-gate-mapper-powerpc64_e5500").is_file())
            self.assertIn("Checking 'python'... failed.", result.stdout)
            self.assertIn("bypassed only for missing Python 2", result.stderr)

    def test_legacy_prerequisite_bypass_rejects_any_non_python2_failure(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sdk = base / "sdk"
            env = self._fake_environment(sdk, "powerpc64_e5500")
            env["REMOTE_GATE_SDK_FORCE_PREREQ"] = "1"
            env["FAKE_PREREQ_FAILURE"] = "other"
            result = subprocess.run(
                ["sh", str(BUILD_SDK), str(sdk), "powerpc64_e5500", str(base / "out")],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("prerequisite bypass refused", result.stderr)
            self.assertFalse((sdk / "build_dir").exists())

    def test_non_legacy_path_rejects_build_id_workaround(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sdk = base / "sdk"
            env = self._fake_environment(sdk, "powerpc64_e5500")
            env["REMOTE_GATE_SDK_LINK_FLAGS"] = "-Wl,--build-id=sha1"
            result = subprocess.run(
                ["sh", str(BUILD_SDK), str(sdk), "powerpc64_e5500", str(base / "out")],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("restricted to the legacy SDK path", result.stderr)
            self.assertFalse((sdk / "build_dir").exists())

    def test_legacy_path_rejects_arbitrary_link_flags(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sdk = base / "sdk"
            env = self._fake_environment(sdk, "powerpc64_e5500")
            env["REMOTE_GATE_SDK_FORCE_PREREQ"] = "1"
            env["REMOTE_GATE_SDK_LINK_FLAGS"] = "-Wl,--gc-sections"
            result = subprocess.run(
                ["sh", str(BUILD_SDK), str(sdk), "powerpc64_e5500", str(base / "out")],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid REMOTE_GATE_SDK_LINK_FLAGS", result.stderr)
            self.assertFalse((sdk / "build_dir").exists())

    def test_legacy_path_binds_sdk_topdir_and_no_longer_relies_on_force(self):
        source = BUILD_SDK.read_text(encoding="utf-8")
        self.assertIn("prepare_legacy_prereq_stamp", source)
        self.assertIn('make TOPDIR="$SDK_ROOT/" -r -s -f "$prereq_mk" prereq', source)
        self.assertIn('touch "$prereq_stamp"', source)
        self.assertIn("'-Wl,--build-id=sha1'", source)
        self.assertIn("restricted to the legacy SDK path", source)
        self.assertNotIn("make FORCE=1", source)
        self.assertNotIn("FORCE=1 make", source)


if __name__ == "__main__":
    unittest.main()
