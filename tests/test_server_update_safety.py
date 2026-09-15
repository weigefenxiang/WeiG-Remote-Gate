from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
UPDATE = (ROOT / "server" / "update.sh").read_text(encoding="utf-8")


class ServerUpdateSafetyTests(unittest.TestCase):
    def test_target_updater_can_bootstrap_future_manifests(self):
        self.assertIn("REMOTE_GATE_UPDATER_BOOTSTRAPPED", UPDATE)
        self.assertIn('"${RAW_BASE}/server/update.sh"', UPDATE)
        self.assertIn('REMOTE_GATE_BUILD_SHA="$BUILD_SHA"', UPDATE)

    def test_client_profile_runtime_files_are_part_of_the_update_manifest(self):
        self.assertIn('"server/profile-entry.py"', UPDATE)
        self.assertIn('"server/app/client_profiles.py"', UPDATE)
        self.assertIn('"server/app/control_queue.py"', UPDATE)
        self.assertIn('test -x "$LIB_DIR/profile-entry.py"', UPDATE)

    def test_backup_container_is_private_without_destroying_archived_modes(self):
        self.assertNotIn('chmod -R go-rwx "$BACKUP"', UPDATE)
        self.assertIn('chmod 0700 "$BACKUP"', UPDATE)

    def test_rollback_repairs_runtime_permissions_and_proves_health(self):
        self.assertIn("normalize_runtime_permissions()", UPDATE)
        self.assertIn('systemctl reset-failed "$SERVICE_NAME"', UPDATE)
        self.assertIn("rollback_health_check()", UPDATE)
        self.assertIn("Rollback restored previous files and health check passed.", UPDATE)
        self.assertIn("rollback restored files but service health check failed", UPDATE)


if __name__ == "__main__":
    unittest.main()
