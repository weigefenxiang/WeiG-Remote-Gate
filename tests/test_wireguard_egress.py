import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "openwrt/remote-gate-wireguard-egress.sh"


class WireGuardEgressTests(unittest.TestCase):
    def test_shell_syntax(self):
        subprocess.run(["sh", "-n", str(SCRIPT)], check=True)

    def test_full_tunnel_is_optional_parameterized_and_reversible(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("enable <wireguard-interface> <wan-interface>", source)
        self.assertIn("remote_gate_wg_egress_forward", source)
        self.assertIn("remote_gate_wg_egress_nat", source)
        self.assertIn("target=MASQUERADE", source)
        self.assertIn("table=$ROUTE_TABLE", source)
        self.assertIn("AllowedIPs = 0.0.0.0/0", source)
        self.assertIn("disable_egress", source)
        self.assertNotIn("163.204.223.16", source)

    def test_private_and_lan_ranges_stay_on_main_table(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for cidr in ("10.0.0.0/8", "100.64.0.0/10", "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16"):
            self.assertIn(cidr, source)
        self.assertIn("lookup=main", source)
        self.assertIn("lookup=$ROUTE_TABLE", source)

    def test_remote_gate_input_firewall_is_not_reused_for_egress(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("remote-gate-firewall.sh", source)
        self.assertIn("separate from Remote Gate INPUT protection", source)


if __name__ == "__main__":
    unittest.main()
