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
            "  *' package/weig-remote-gate-mapper/compile '*)\n"
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


if __name__ == "__main__":
    unittest.main()
