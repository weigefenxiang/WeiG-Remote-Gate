from pathlib import Path
import os
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "shared" / "backup-retention.sh"
SERVER_UPDATE = (ROOT / "server" / "update.sh").read_text(encoding="utf-8")
OPENWRT_UPDATE = (ROOT / "openwrt" / "update.sh").read_text(encoding="utf-8")


class BackupRetentionTests(unittest.TestCase):
    def run_helper(self, current: Path, legacy: Path | None = None, keep: str = "2") -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["REMOTE_GATE_BACKUP_KEEP"] = keep
        script = f'''
set -eu
. "{HELPER}"
remote_gate_retain_backups "{current}" "{legacy or ''}"
'''
        return subprocess.run(
            ["sh", "-c", script],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_keeps_only_newest_two_project_timestamp_directories(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "backups"
            root.mkdir()
            names = [
                "20260901T010101Z",
                "20260902T010101Z",
                "20260903T010101Z",
                "20260904T010101Z",
            ]
            for name in names:
                (root / name).mkdir()
            (root / "manual-backup").mkdir()
            (root / "README").write_text("keep me", encoding="utf-8")

            result = self.run_helper(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                sorted(p.name for p in root.iterdir() if p.is_dir() and p.name[0].isdigit()),
                ["20260903T010101Z", "20260904T010101Z"],
            )
            self.assertTrue((root / "manual-backup").is_dir())
            self.assertTrue((root / "README").is_file())

    def test_legacy_tmp_backups_join_global_newest_two_then_migrate_to_var_root(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            current = base / "var" / "backups" / "weig-remote-gate"
            legacy = base / "tmp" / "backups" / "weig-remote-gate"
            current.mkdir(parents=True)
            legacy.mkdir(parents=True)
            (current / "20260915T140000Z").mkdir()
            (legacy / "20260914T120000Z").mkdir()
            (legacy / "20260915T130000Z").mkdir()
            (legacy / "not-project-owned").mkdir()

            result = self.run_helper(current, legacy)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((current / "20260915T140000Z").is_dir())
            self.assertTrue((current / "20260915T130000Z").is_dir())
            self.assertFalse((legacy / "20260914T120000Z").exists())
            self.assertTrue((legacy / "not-project-owned").is_dir())

    def test_invalid_retention_value_falls_back_to_two(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "backups"
            root.mkdir()
            for idx in range(1, 5):
                (root / f"2026090{idx}T010101Z").mkdir()
            result = self.run_helper(root, keep="999")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len([p for p in root.iterdir() if p.is_dir()]), 2)

    def test_both_updaters_prune_only_after_success_and_use_shared_owner(self):
        for source in (SERVER_UPDATE, OPENWRT_UPDATE):
            self.assertIn("shared/backup-retention.sh", source)
            self.assertIn("remote_gate_retain_backups", source)
            self.assertIn("SUCCESS=1", source)
            self.assertLess(source.index("SUCCESS=1"), source.rindex("remote_gate_retain_backups"))
        self.assertIn('/tmp/backups/weig-remote-gate', OPENWRT_UPDATE)


if __name__ == "__main__":
    unittest.main()
