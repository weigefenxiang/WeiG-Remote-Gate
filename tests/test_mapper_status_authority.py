from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALL = (ROOT / "openwrt" / "install.sh").read_text(encoding="utf-8")
UPDATE = (ROOT / "openwrt" / "update.sh").read_text(encoding="utf-8")
AUDIT = (ROOT / "openwrt" / "remote-gate-audit.sh").read_text(encoding="utf-8")
MAPPING = (ROOT / "openwrt" / "remote-gate-mapping.sh").read_text(encoding="utf-8")


class MapperStatusAuthorityTests(unittest.TestCase):
    def test_install_summary_uses_integrity_authority(self):
        self.assertIn('if sh "$MAPPER_INSTALLER" current', INSTALL)
        self.assertIn('Mapped Access mapper integrity current:', INSTALL)
        self.assertNotIn('if [ -x "$LIB_DIR/remote-gate-mapper" ]; then MAPPER_AVAILABLE=yes; fi', INSTALL)

    def test_update_summary_uses_integrity_authority(self):
        self.assertIn('remote-gate-mapper-install.sh" current', UPDATE)

    def test_audit_reports_delivery_integrity_and_runtime_authority(self):
        self.assertIn('MAPPER_INSTALLER=', AUDIT)
        self.assertIn('status-json', AUDIT)
        self.assertIn('Mapper runtime authority: current', AUDIT)
        self.assertIn('NOT CURRENT (Mapped Access must remain unavailable)', AUDIT)
        self.assertNotIn('Mapper binary: available', AUDIT)

    def test_mapping_runtime_uses_same_current_authority(self):
        self.assertIn('sh "$MAPPER_INSTALLER" current', MAPPING)
        self.assertIn('mapper-integrity-unavailable', MAPPING)


if __name__ == "__main__":
    unittest.main()
