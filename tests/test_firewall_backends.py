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
        self.assertIn('iptables -I INPUT 1 -j "$FW3_CHAIN_V4"', source)
        self.assertIn('ip6tables -I INPUT 1 -j "$FW3_CHAIN_V6"', source)
        self.assertIn('chain-pre/input/90-weig-remote-gate.nft', source)

    def test_ipv6_only_controls_echo_request_and_wireguard_udp(self):
        source = FIREWALL.read_text(encoding="utf-8")
        self.assertIn("--icmpv6-type echo-request", source)
        self.assertIn("-p udp --dport", source)
        self.assertIn("icmpv6 type echo-request", source)
        self.assertNotIn("--icmpv6-type neighbour", source.lower())
        self.assertNotIn("--icmpv6-type router", source.lower())
        self.assertNotIn("--icmpv6-type packet-too-big", source.lower())

    def test_scope_can_keep_ping_closed(self):
        source = FIREWALL.read_text(encoding="utf-8")
        self.assertIn('if [ "$AUTH_SCOPE" = "wg_ping" ]', source)
        self.assertIn('valid_scope() { case "$1" in wg|wg_ping)', source)

    def test_agent_syncs_dual_stack_wans_and_wireguard_ports(self):
        source = AGENT.read_text(encoding="utf-8")
        self.assertIn("v4_protected_devices", source)
        self.assertIn("v6_protected_devices", source)
        self.assertIn("wireguard_ports", source)
        self.assertIn('"$FIREWALL" sync "$v4" "$v6" "$ports"', source)

    def test_agent_uses_health_based_transport_candidates(self):
        source = AGENT.read_text(encoding="utf-8")
        self.assertIn("control_candidates", source)
        self.assertIn("remember_control_path", source)
        self.assertIn('flag="-6"', source)
        self.assertIn('flag="-4"', source)


if __name__ == "__main__":
    unittest.main()
