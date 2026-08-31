import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "openwrt/remote-gate-wireguard-egress.sh"
INSTALL = ROOT / "openwrt/install.sh"
UPDATE = ROOT / "openwrt/update.sh"
UNINSTALL = ROOT / "openwrt/uninstall.sh"


class WireGuardEgressTests(unittest.TestCase):
    def test_shell_syntax(self):
        for path in (SCRIPT, INSTALL, UPDATE, UNINSTALL):
            subprocess.run(["sh", "-n", str(path)], check=True)

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

    def test_installer_updater_and_uninstaller_own_optional_helper(self):
        install = INSTALL.read_text(encoding="utf-8")
        update = UPDATE.read_text(encoding="utf-8")
        uninstall = UNINSTALL.read_text(encoding="utf-8")
        self.assertIn('fetch_file "remote-gate-wireguard-egress.sh"', install)
        self.assertIn("remote-gate-wireguard-egress.sh", update)
        self.assertIn('"$LIB_DIR/remote-gate-wireguard-egress.sh" disable', uninstall)
        self.assertIn("remote_gate_wg_egress_forward", uninstall)
        self.assertIn("remote_gate_wg_egress_default_rule", uninstall)


if __name__ == "__main__":
    unittest.main()
