import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIREWALL = ROOT / "openwrt" / "remote-gate-firewall.sh"
AGENT = ROOT / "openwrt" / "remote-gate-agent.sh"


def fake_cmd(directory: Path, name: str, body: str = "exit 0\n") -> None:
    path = directory / name
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class FirewallBackendTests(unittest.TestCase):
    def run_detect(self, names):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for name in names:
                fake_cmd(directory, name)
            env = os.environ.copy()
            env["PATH"] = f"{directory}:/usr/bin:/bin"
            proc = subprocess.run(
                ["/bin/sh", str(FIREWALL), "detect"],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            return proc.returncode, proc.stdout.strip()

    def test_detects_fw4_first(self):
        self.assertEqual(self.run_detect(["fw4", "nft", "fw3", "iptables", "ipset"]), (0, "fw4-nftables"))

    def test_detects_fw3_ipset(self):
        self.assertEqual(self.run_detect(["fw3", "iptables", "ipset"]), (0, "fw3-iptables"))

    def test_rejects_unsupported_backend(self):
        rc, out = self.run_detect([])
        self.assertNotEqual(rc, 0)
        self.assertEqual(out, "unsupported")

    def test_guard_never_modifies_forward_chain(self):
        source = FIREWALL.read_text(encoding="utf-8")
        self.assertNotIn("-I FORWARD", source)
        self.assertNotIn("-A FORWARD", source)
        self.assertNotIn("chain-pre/forward", source)
        self.assertIn('iptables -I INPUT 1 -j "$FW3_CHAIN"', source)
        self.assertIn('chain-pre/input/90-weig-remote-gate.nft', source)

    def test_only_icmp_echo_and_wireguard_udp_are_guarded(self):
        source = FIREWALL.read_text(encoding="utf-8")
        self.assertIn("--icmp-type echo-request", source)
        self.assertIn("-p udp --dport", source)
        self.assertIn("icmp type echo-request", source)
        self.assertIn("udp dport @weig_remote_gate_protected_udp_port", source)
        self.assertNotIn("-p tcp --dport", source)

    def test_agent_syncs_public_wans_and_wireguard_ports(self):
        source = AGENT.read_text(encoding="utf-8")
        self.assertIn("public_wan_devices", source)
        self.assertIn("wireguard_ports", source)
        self.assertIn("listen_port", source)
        self.assertIn("uci -q show network", source)
        self.assertIn('"$FIREWALL" sync "$devices" "$ports"', source)


if __name__ == "__main__":
    unittest.main()
