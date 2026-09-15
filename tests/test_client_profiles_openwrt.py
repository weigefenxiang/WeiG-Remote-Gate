from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ClientProfilesOpenWrtContractTests(unittest.TestCase):
    def test_profile_helper_fails_closed_and_never_persists_private_key(self):
        text = (ROOT / "openwrt" / "remote-gate-client-profiles.sh").read_text(encoding="utf-8")
        self.assertIn("profile-ownership-mismatch", text)
        self.assertIn("owned_section()", text)
        self.assertIn("ipv4_is_used()", text)
        self.assertIn("base+1", text)
        self.assertIn("x<last", text)
        self.assertIn('description=remote-gate:${profile_id}', text)
        metadata_part = text.split('result_tmp="${saved_result}.tmp.$$"', 1)[0]
        self.assertNotIn('"private_key"', metadata_part)
        self.assertIn('"private_key":"$private_key"', text)

    def test_partial_create_rolls_back_live_and_persistent_peer(self):
        text = (ROOT / "openwrt" / "remote-gate-client-profiles.sh").read_text(encoding="utf-8")
        self.assertIn("cleanup_created_peer()", text)
        self.assertIn('cleanup_created_peer "$wg_name" "$public_key" "$section"', text)
        metadata = text.split('meta_tmp="${meta}.tmp.$$"', 1)[1].split('result_tmp="${saved_result}.tmp.$$"', 1)[0]
        self.assertIn('cleanup_created_peer "$wg_name" "$public_key" "$section"', metadata)
        self.assertIn("profile-metadata-write-failed", metadata)

    def test_scheduler_uses_existing_serialized_agent_pull_channel(self):
        text = (ROOT / "openwrt" / "remote-gate-report.sh").read_text(encoding="utf-8")
        self.assertIn('/api/v1/agent/pull', text)
        self.assertIn('/api/v1/agent/profile-result', text)
        self.assertIn('/api/v1/agent/profiles-status', text)
        self.assertNotIn('/api/v1/agent/profile-pull', text)

    def test_install_update_and_uninstall_cover_profile_lifecycle(self):
        install = (ROOT / "openwrt" / "install.sh").read_text(encoding="utf-8")
        update = (ROOT / "openwrt" / "update.sh").read_text(encoding="utf-8")
        uninstall = (ROOT / "openwrt" / "uninstall.sh").read_text(encoding="utf-8")
        self.assertIn('remote-gate-client-profiles.sh', install)
        self.assertIn('client_profiles_owned=1', install)
        self.assertIn('remote-gate-client-profiles.sh', update)
        self.assertIn('client_profiles_owned=1', update)
        self.assertIn('revoke-all', uninstall)
        self.assertIn('profile-ownership-mismatch', (ROOT / "openwrt" / "remote-gate-client-profiles.sh").read_text(encoding="utf-8"))

    def test_vps_profile_entry_does_not_duplicate_agent_status_authority(self):
        entry = (ROOT / "server" / "profile-entry.py").read_text(encoding="utf-8")
        self.assertNotIn('path == "/api/v1/agent/status"', entry)
        self.assertIn('/api/v1/agent/profile-result', entry)
        self.assertIn('/api/v1/agent/profiles-status', entry)
        self.assertNotIn('localStorage', entry)
        self.assertNotIn('sessionStorage', entry)


if __name__ == "__main__":
    unittest.main()
