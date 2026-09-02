import os
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIREWALL = ROOT / "openwrt/remote-gate-firewall.sh"


def fake_cmd(directory: Path, name: str, body: str = "exit 0\n") -> None:
    path = directory / name
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class Fw4RestoreRuntimeTests(unittest.TestCase):
    def run_restore(self, *, auth_port=54321, control_port=54321):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        fake_bin = root / "bin"
        fake_bin.mkdir()
        state_base = root / "state"
        state = state_base / "firewall"
        auth_v4 = state / "authorization-ipv4.d"
        auth_v6 = state / "authorization-ipv6.d"
        auth_v4.mkdir(parents=True)
        auth_v6.mkdir(parents=True)
        nft_log = root / "nft.log"

        (state / "backend").write_text("fw4-nftables\n", encoding="utf-8")
        (state / "protected-devices-v4").write_text("pppoe-WAN\n", encoding="utf-8")
        (state / "protected-devices-v6").write_text("", encoding="utf-8")
        (state / "protected-ports").write_text("41194\n", encoding="utf-8")
        (state / "mapped-ingress-v4").write_text("pppoe-WAN|54321\n", encoding="utf-8")
        (state / "mapped-control-v4").write_text(
            f"pppoe-WAN|{control_port}|74.125.250.129|19302\n",
            encoding="utf-8",
        )

        expires = int(time.time()) + 600
        auth_file = auth_v4 / "198.51.100.7"
        auth_file.write_text(
            "\n".join(
                [
                    "198.51.100.7",
                    "pppoe-WAN",
                    str(auth_port),
                    str(expires),
                    "ipv4",
                    "wg",
                    "web_observed",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        fake_cmd(fake_bin, "fw4")
        fake_cmd(
            fake_bin,
            "nft",
            """if [ "${1:-}" = "list" ]; then
    exit 0
fi
if [ "${1:-}" = "flush" ]; then
    exit 0
fi
if [ "${1:-}" = "-f" ] && [ "${2:-}" = "-" ]; then
    cat >> "$REMOTE_GATE_NFT_LOG"
    printf '\n' >> "$REMOTE_GATE_NFT_LOG"
    exit 0
fi
exit 0
""",
        )

        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:/usr/bin:/bin"
        env["REMOTE_GATE_STATE_DIR"] = str(state_base)
        env["REMOTE_GATE_LIB_DIR"] = str(ROOT / "openwrt")
        env["REMOTE_GATE_NFT_LOG"] = str(nft_log)
        proc = subprocess.run(
            ["/bin/sh", str(FIREWALL), "restore"],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        log = nft_log.read_text(encoding="utf-8") if nft_log.exists() else ""
        return proc, log, auth_file

    def test_restore_rebuilds_current_mapped_and_authorized_tuple(self):
        proc, log, auth_file = self.run_restore()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(auth_file.exists())
        self.assertIn(
            'add element inet fw4 weig_remote_gate_mapped_ingress_v4 { "pppoe-WAN" . 54321 }',
            log,
        )
        self.assertIn(
            'add element inet fw4 weig_remote_gate_mapped_control_v4 { "pppoe-WAN" . 54321 . 74.125.250.129 . 19302 }',
            log,
        )
        self.assertIn("add element inet fw4 weig_remote_gate_auth_ipv4 { 198.51.100.7 timeout", log)
        self.assertIn('add element inet fw4 weig_remote_gate_auth_ifname_v4 { "pppoe-WAN" }', log)
        self.assertIn("add element inet fw4 weig_remote_gate_auth_udp_port_v4 { 54321 }", log)

    def test_restore_revokes_authorization_for_stale_mapped_ingress(self):
        proc, log, auth_file = self.run_restore(auth_port=53000)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(auth_file.exists())
        self.assertNotIn("weig_remote_gate_auth_ipv4 { 198.51.100.7", log)
        self.assertNotIn("weig_remote_gate_auth_udp_port_v4 { 53000 }", log)
        self.assertIn(
            'add element inet fw4 weig_remote_gate_mapped_ingress_v4 { "pppoe-WAN" . 54321 }',
            log,
        )

    def test_restore_drops_stale_stun_control_tuple(self):
        proc, log, _auth_file = self.run_restore(control_port=53000)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("weig_remote_gate_mapped_control_v4", log)
        self.assertIn(
            'add element inet fw4 weig_remote_gate_mapped_ingress_v4 { "pppoe-WAN" . 54321 }',
            log,
        )


if __name__ == "__main__":
    unittest.main()
