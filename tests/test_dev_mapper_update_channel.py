from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
UPDATE = (ROOT / "openwrt" / "update.sh").read_text(encoding="utf-8")


class DevMapperUpdateChannelTests(unittest.TestCase):
    def test_dev_updates_use_dev_mapper_channel(self):
        self.assertIn('[ "$RAW_REF" = dev ] && mapper_channel=dev', UPDATE)
        self.assertIn('"install-$mapper_channel"', UPDATE)

    def test_stable_updates_keep_release_channel_default(self):
        self.assertIn('mapper_channel=release', UPDATE)

    def test_stale_backup_self_copy_is_absent(self):
        self.assertNotIn('cp -a "$BACKUP/remote-gate-agent.init" "$BACKUP/remote-gate-agent.init"', UPDATE)


if __name__ == "__main__":
    unittest.main()
