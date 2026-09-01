from pathlib import Path
import hashlib
import os
import stat
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "openwrt" / "remote-gate-mapper-install.sh"
BOOTSTRAP = ROOT / "openwrt" / "install-mapper.sh"
DEV_WORKFLOW = (ROOT / ".github" / "workflows" / "mapper-dev.yml").read_text(encoding="utf-8")
AGENT = (ROOT / "openwrt" / "remote-gate-agent.sh").read_text(encoding="utf-8")
SDK_BUILDER = (ROOT / "native" / "build-openwrt-sdk.sh").read_text(encoding="utf-8")


def fake_mapper(path: Path, marker: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/sh\n"
        "if [ \"${1:-}\" = --version ]; then echo 'remote-gate-mapper 0.3.17 api=1'; exit 0; fi\n"
        f"echo 'usage: {marker}' >&2\n"
        "exit 2\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class MapperLifecycleTests(unittest.TestCase):
    def _env(self, root: Path):
        lib = root / "lib"
        state = root / "state"
        lib.mkdir(); state.mkdir()
        (lib / "VERSION").write_text("0.3.17\n", encoding="utf-8")
        platform = root / "platform.sh"
        platform.write_text(
            "#!/bin/sh\n"
            "[ \"${1:-}\" = mapper-abi ] && { echo aarch64_cortex-a53; exit 0; }\n"
            "exit 1\n",
            encoding="utf-8",
        )
        platform.chmod(0o755)
        env = os.environ.copy()
        env.update({
            "REMOTE_GATE_LIB_DIR": str(lib),
            "REMOTE_GATE_STATE_DIR": str(state),
            "REMOTE_GATE_PLATFORM": str(platform),
            "REMOTE_GATE_VERSION_FILE": str(lib / "VERSION"),
            "REMOTE_GATE_MAPPER_DEST": str(lib / "remote-gate-mapper"),
            "REMOTE_GATE_MAPPER_META": str(lib / "remote-gate-mapper.meta"),
            "REMOTE_GATE_MAPPER_BACKUP_DIR": str(state / "mapper-backup"),
            "REMOTE_GATE_MAPPING_HELPER": str(root / "missing-mapping"),
            "REMOTE_GATE_AGENT_HELPER": str(root / "missing-agent"),
        })
        return env, lib, state

    def test_install_replace_rollback_and_uninstall(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            env, lib, state = self._env(root)
            first = root / "first"
            second = root / "second"
            fake_mapper(first, "first")
            fake_mapper(second, "second")

            subprocess.run(["sh", str(INSTALLER), "install-local", str(first)], env=env, check=True)
            subprocess.run(["sh", str(INSTALLER), "install-local", str(second)], env=env, check=True)
            status = subprocess.check_output(["sh", str(INSTALLER), "status-json"], env=env, text=True)
            self.assertIn('"ready":true', status)
            self.assertIn('"rollback_available":true', status)

            subprocess.run(["sh", str(INSTALLER), "rollback"], env=env, check=True)
            result = subprocess.run([str(lib / "remote-gate-mapper")], text=True, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 2)
            self.assertIn("usage: first", result.stderr)

            subprocess.run(["sh", str(INSTALLER), "uninstall"], env=env, check=True)
            self.assertFalse((lib / "remote-gate-mapper").exists())
            self.assertFalse((lib / "remote-gate-mapper.meta").exists())
            self.assertFalse((state / "mapper-backup").exists())

    def test_dev_install_requires_exact_abi_hash_and_self_identity(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            env, lib, _state = self._env(root)
            assets = root / "assets"
            asset_rel = Path("remote-gate-mapper-aarch64")
            mapper = assets / asset_rel
            fake_mapper(mapper, "dev")
            digest = hashlib.sha256(mapper.read_bytes()).hexdigest()
            manifest = root / "dev-manifest.tsv"
            manifest.write_text(
                "# schema=1\n# version=0.3.17\n# mapper_api=1\n"
                "# package_abi\tbuild_class\tasset\tsha256\tstatus\n"
                f"aarch64_cortex-a53\taarch64\t{asset_rel.as_posix()}\t{digest}\tdev-candidate\n",
                encoding="utf-8",
            )
            env.update({
                "REMOTE_GATE_MAPPER_DEV_MANIFEST_FILE": str(manifest),
                "REMOTE_GATE_MAPPER_DEV_ASSET_DIR": str(assets),
            })
            subprocess.run(["sh", str(INSTALLER), "install-dev"], env=env, check=True)
            meta = (lib / "remote-gate-mapper.meta").read_text(encoding="utf-8")
            self.assertIn("package_abi=aarch64_cortex-a53", meta)
            self.assertIn("source=dev", meta)

            manifest.write_text(manifest.read_text(encoding="utf-8").replace(digest, "0" * 64), encoding="utf-8")
            result = subprocess.run(["sh", str(INSTALLER), "install-dev"], env=env)
            self.assertNotEqual(result.returncode, 0)
            subprocess.run(["sh", str(INSTALLER), "current"], env=env, check=True)

    def test_dev_release_is_current_device_only_and_smoked(self):
        self.assertIn("aarch64_cortex-a53", DEV_WORKFLOW)
        self.assertIn("remote-gate-mapper-aarch64.gz", DEV_WORKFLOW)
        self.assertIn("sh native/smoke-portable.sh aarch64", DEV_WORKFLOW)
        self.assertIn("mapper-dev-v$version", DEV_WORKFLOW)
        self.assertIn("dev-candidate", DEV_WORKFLOW)

    def test_mapper_bootstrap_has_explicit_release_or_dev_channel(self):
        text = BOOTSTRAP.read_text(encoding="utf-8")
        self.assertIn("release|dev", text)
        self.assertIn("install-dev", text)
        self.assertIn("install", text)
        self.assertIn("Remote Gate version mismatch", text)

    def test_lifecycle_commands_are_exposed(self):
        text = INSTALLER.read_text(encoding="utf-8")
        for command in ("install", "update", "repair", "rollback", "uninstall", "status", "status-json"):
            self.assertIn(command, text)
        self.assertIn("mapper-backup", text)
        self.assertIn("stop-all", text)
        self.assertIn("sync-firewall", text)

    def test_sdk_runner_recovers_packaged_mapper_after_openwrt_autoremove(self):
        self.assertIn(".pkgdir/remote-gate-mapper/usr/lib/remote-gate/remote-gate-mapper", SDK_BUILDER)
        self.assertIn("ipkg-*/remote-gate-mapper/usr/lib/remote-gate/remote-gate-mapper", SDK_BUILDER)

    def test_mapping_candidates_still_require_ipv4_default_route(self):
        self.assertIn('[ -f "$base.def4" ] && [ -s "$base.v4" ] || continue', AGENT)
        self.assertIn('is_public_ipv4 "$address" && has_public=1', AGENT)
        self.assertIn('[ "$has_public" -eq 0 ] || continue', AGENT)


if __name__ == "__main__":
    unittest.main()
