from pathlib import Path
import hashlib
import os
import stat
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
ABI_MAP = ROOT / "native" / "mapper-abi-map.tsv"
BUILDER = ROOT / "native" / "build-release-assets.sh"
INSTALLER = ROOT / "openwrt" / "remote-gate-mapper-install.sh"
INSTALL_SH = (ROOT / "openwrt" / "install.sh").read_text(encoding="utf-8")
UPDATE_SH = (ROOT / "openwrt" / "update.sh").read_text(encoding="utf-8")
RELEASE_CI = (ROOT / ".github" / "workflows" / "mapper-release.yml").read_text(encoding="utf-8")


def abi_rows():
    rows = []
    for raw in ABI_MAP.read_text(encoding="utf-8").splitlines():
        if not raw or raw.startswith("#"):
            continue
        abi, build_class, delivery = raw.split("\t")
        rows.append((abi, build_class, delivery))
    return rows


def fake_mapper(path: Path, version: str = "0.3.17"):
    path.write_text(
        "#!/bin/sh\n"
        f"if [ \"${{1:-}}\" = --version ]; then echo 'remote-gate-mapper {version} api=1'; exit 0; fi\n"
        "echo usage: fake >&2\n"
        "exit 2\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class MapperReleaseDeliveryTests(unittest.TestCase):
    def test_release_builder_emits_only_exact_portable_abis(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            classes = root / "classes"
            out = root / "release"
            classes.mkdir()
            for build_class in {row[1] for row in abi_rows() if row[2] == "cross-candidate"}:
                fake_mapper(classes / f"remote-gate-mapper-{build_class}")
            env = os.environ.copy()
            env["REMOTE_GATE_RELEASE_COMMIT"] = "a" * 40
            subprocess.run(["sh", str(BUILDER), str(classes), str(out)], check=True, env=env)

            manifest = (out / "remote-gate-mapper-manifest.tsv").read_text(encoding="utf-8")
            self.assertIn("# schema=1", manifest)
            self.assertIn("# version=0.3.17", manifest)
            self.assertIn("# mapper_api=1", manifest)
            data = [line.split("\t") for line in manifest.splitlines() if line and not line.startswith("#")]
            expected = {row[0] for row in abi_rows() if row[2] == "cross-candidate"}
            self.assertEqual({row[0] for row in data}, expected)
            self.assertTrue(all(row[4] == "released" for row in data))
            self.assertFalse({row[0] for row in abi_rows() if row[2] == "sdk-required"} & {row[0] for row in data})
            for abi, _build_class, asset, sha256, _status in data:
                payload = (out / asset).read_bytes()
                self.assertEqual(hashlib.sha256(payload).hexdigest(), sha256, abi)

    def test_router_installer_exact_abi_hash_identity_and_atomic_install(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            lib = root / "lib"
            assets = root / "assets"
            lib.mkdir(); assets.mkdir()
            version = lib / "VERSION"
            version.write_text("0.3.17\n", encoding="utf-8")
            platform = lib / "remote-gate-platform.sh"
            platform.write_text("#!/bin/sh\n[ \"$1\" = mapper-abi ] && { echo x86_64; exit 0; }\nexit 1\n", encoding="utf-8")
            mapper = assets / "remote-gate-mapper-x86_64"
            fake_mapper(mapper)
            digest = hashlib.sha256(mapper.read_bytes()).hexdigest()
            manifest = root / "manifest.tsv"
            manifest.write_text(
                "# schema=1\n# version=0.3.17\n# tag=v0.3.17\n# mapper_api=1\n# commit=" + "a" * 40 + "\n"
                "# package_abi\tbuild_class\tasset\tsha256\tstatus\n"
                f"x86_64\tx86_64\t{mapper.name}\t{digest}\treleased\n",
                encoding="utf-8",
            )
            dest = lib / "remote-gate-mapper"
            env = os.environ.copy()
            env.update({
                "REMOTE_GATE_LIB_DIR": str(lib),
                "REMOTE_GATE_PLATFORM": str(platform),
                "REMOTE_GATE_VERSION_FILE": str(version),
                "REMOTE_GATE_MAPPER_DEST": str(dest),
                "REMOTE_GATE_MAPPER_META": str(lib / "remote-gate-mapper.meta"),
                "REMOTE_GATE_MAPPER_MANIFEST_FILE": str(manifest),
                "REMOTE_GATE_MAPPER_ASSET_DIR": str(assets),
            })
            subprocess.run(["sh", str(INSTALLER), "install-release"], check=True, env=env)
            self.assertEqual(dest.read_bytes(), mapper.read_bytes())
            meta = (lib / "remote-gate-mapper.meta").read_text(encoding="utf-8")
            self.assertIn("version=0.3.17", meta)
            self.assertIn("mapper_api=1", meta)
            self.assertIn("package_abi=x86_64", meta)
            self.assertIn("source=released", meta)
            subprocess.run(["sh", str(INSTALLER), "current"], check=True, env=env)

            old = dest.read_bytes()
            manifest.write_text(manifest.read_text(encoding="utf-8").replace(digest, "0" * 64), encoding="utf-8")
            result = subprocess.run(["sh", str(INSTALLER), "install-release"], env=env)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(dest.read_bytes(), old)
            self.assertTrue(os.access(dest, os.X_OK), "a still-current mapper must not be quarantined on manifest failure")

    def test_stale_or_wrong_self_version_is_quarantined(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            lib = root / "lib"
            assets = root / "assets"
            lib.mkdir(); assets.mkdir()
            (lib / "VERSION").write_text("0.3.17\n", encoding="utf-8")
            platform = lib / "remote-gate-platform.sh"
            platform.write_text("#!/bin/sh\n[ \"$1\" = mapper-abi ] && { echo x86_64; exit 0; }\nexit 1\n", encoding="utf-8")
            dest = lib / "remote-gate-mapper"
            fake_mapper(dest, version="0.3.16")
            digest = hashlib.sha256(dest.read_bytes()).hexdigest()
            (lib / "remote-gate-mapper.meta").write_text(
                "schema=1\nversion=0.3.17\nmapper_api=1\npackage_abi=x86_64\nbuild_class=x86_64\n"
                f"asset=old\nsha256={digest}\nsource=released\n",
                encoding="utf-8",
            )
            manifest = root / "manifest.tsv"
            manifest.write_text("# schema=1\n# version=0.3.17\n# tag=v0.3.17\n# mapper_api=1\n", encoding="utf-8")
            env = os.environ.copy()
            env.update({
                "REMOTE_GATE_LIB_DIR": str(lib),
                "REMOTE_GATE_PLATFORM": str(platform),
                "REMOTE_GATE_VERSION_FILE": str(lib / "VERSION"),
                "REMOTE_GATE_MAPPER_DEST": str(dest),
                "REMOTE_GATE_MAPPER_META": str(lib / "remote-gate-mapper.meta"),
                "REMOTE_GATE_MAPPER_MANIFEST_FILE": str(manifest),
                "REMOTE_GATE_MAPPER_ASSET_DIR": str(assets),
            })
            result = subprocess.run(["sh", str(INSTALLER), "install-release"], env=env)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(os.access(dest, os.X_OK))
            self.assertNotEqual(subprocess.run(["sh", str(INSTALLER), "current"], env=env).returncode, 0)

    def test_release_workflow_is_main_tip_tag_only_and_manifest_is_last(self):
        self.assertIn("tags:", RELEASE_CI)
        self.assertIn('test "$GITHUB_REF_NAME" = "v$version"', RELEASE_CI)
        self.assertIn('test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"', RELEASE_CI)
        self.assertIn("sh native/smoke-portable.sh", RELEASE_CI)
        self.assertIn("gh release create", RELEASE_CI)
        self.assertIn("--draft", RELEASE_CI)
        self.assertLess(RELEASE_CI.index('[[ "$(basename "$asset")" == remote-gate-mapper-manifest.tsv ]]'), RELEASE_CI.index("gh release upload \"$tag\" native/release/remote-gate-mapper-manifest.tsv"))
        self.assertIn("gh release edit \"$tag\" --draft=false", RELEASE_CI)

    def test_install_and_update_use_release_helper_without_uname_fallback(self):
        self.assertIn('remote-gate-mapper-install.sh', INSTALL_SH)
        self.assertIn('install-release', INSTALL_SH)
        self.assertIn('install-local', INSTALL_SH)
        self.assertIn('remote-gate-mapper-install.sh', UPDATE_SH)
        self.assertIn('install-release', UPDATE_SH)
        helper = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('sh "$PLATFORM" mapper-abi', helper)
        self.assertNotIn('uname -m', helper)
        self.assertIn('sha256sum', helper)
        self.assertIn('identity_binary', helper)
        self.assertIn('mapper_api', helper)
        self.assertIn('[ "$status" = released ]', helper)
        self.assertIn('mv -f "$staged" "$DEST"', helper)
        self.assertIn('quarantine_invalid', helper)


if __name__ == "__main__":
    unittest.main()
