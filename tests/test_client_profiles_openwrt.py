from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
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

    def test_allocator_counts_wireguard_interface_cidr_as_one_host(self):
        text = (ROOT / "openwrt" / "remote-gate-client-profiles.sh").read_text(encoding="utf-8")
        start = text.index("collect_used_ipv4() {")
        end = text.index("\nlan_values() {", start)
        functions = text[start:end]

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bindir = root / "bin"
            state = root / "state"
            runtime = root / "runtime"
            bindir.mkdir()
            state.mkdir()
            runtime.mkdir()

            ip = bindir / "ip"
            ip.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' '29: WG_HOME    inet 10.77.0.1/24 brd 10.77.0.255 scope global WG_HOME'\n",
                encoding="utf-8",
            )
            wg = bindir / "wg"
            wg.write_text(
                "#!/bin/sh\n"
                "if [ \"$*\" = 'show WG_HOME allowed-ips' ]; then\n"
                "  printf '%s\\n' 'peerkey=    10.77.0.2/32 fd77:77:77::2/128'\n"
                "fi\n",
                encoding="utf-8",
            )
            ip.chmod(0o755)
            wg.chmod(0o755)

            shell = (
                "set -eu\n"
                'STATE_DIR="$TEST_STATE_DIR"\n'
                'RUNTIME_DIR="$TEST_RUNTIME_DIR"\n'
                f"{functions}\n"
                "allocate_ipv4 WG_HOME 10.77.0.0/24\n"
            )
            env = dict(os.environ)
            env["PATH"] = f"{bindir}:{env.get('PATH', '')}"
            env["TEST_STATE_DIR"] = str(state)
            env["TEST_RUNTIME_DIR"] = str(runtime)
            process = subprocess.run(
                ["sh", "-c", shell],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(process.stdout.strip(), "10.77.0.3")

    def test_home_networks_does_not_require_paste(self):
        text = (ROOT / "openwrt" / "remote-gate-client-profiles.sh").read_text(encoding="utf-8")
        self.assertNotIn("paste -sd", text)
        start = text.index("home_networks() {")
        end = text.index("\nprofile_dns() {", start)
        function = text[start:end]

        with tempfile.TemporaryDirectory() as td:
            bindir = Path(td) / "bin"
            bindir.mkdir()
            for name in ("awk", "sed", "tr"):
                source = shutil.which(name)
                self.assertIsNotNone(source)
                os.symlink(source, bindir / name)

            shell = (
                "set -eu\n"
                "WG_PROFILE_HOME_NETWORKS='192.168.1.0/24,10.77.0.0/24,192.168.1.0/24'\n"
                f"{function}\n"
                "home_networks 10.77.0.0/24\n"
            )
            env = dict(os.environ)
            env["PATH"] = str(bindir)
            process = subprocess.run(
                [shutil.which("sh") or "/bin/sh", "-c", shell],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(process.stdout.strip(), "192.168.1.0/24,10.77.0.0/24")

    def test_profile_network_preflight_precedes_peer_side_effects(self):
        text = (ROOT / "openwrt" / "remote-gate-client-profiles.sh").read_text(encoding="utf-8")
        start = text.index("create_profile() {")
        end = text.index("\nlist_json() {", start)
        create = text[start:end]
        side_effect = create.index('wg set "$wg_name" peer "$public_key"')
        self.assertLess(create.index('networks="$(home_networks "$pool")"'), side_effect)
        self.assertLess(create.index('dns="$(profile_dns)"'), side_effect)
        self.assertLess(create.index('networks_json="$(csv_json_array "$networks")"'), side_effect)
        self.assertIn("profile-network-preflight-failed", create)

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
        self.assertIn('terminal_control_error(STORE, command_id, "profile_create")', entry)
        self.assertIn('{"state": "failed", "error": terminal_error}', entry)
        self.assertNotIn('localStorage', entry)
        self.assertNotIn('sessionStorage', entry)


if __name__ == "__main__":
    unittest.main()
