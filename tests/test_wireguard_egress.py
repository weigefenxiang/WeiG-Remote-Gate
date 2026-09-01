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
        self.assertIn("[ipv4|ipv6|dual]", source)
        self.assertIn('RUNTIME_DIR="${REMOTE_GATE_RUNTIME_DIR:-/tmp/remote-gate}"', source)
        self.assertIn("WEIG_WG_EGRESS", source)
        self.assertIn("-j MASQUERADE", source)
        self.assertIn("counter masquerade", source)
        self.assertIn("choose_route_table -4 51820 51879", source)
        self.assertIn("choose_route_table -6 52020 52079", source)
        self.assertIn("AllowedIPs = 0.0.0.0/0, ::/0", source)
        self.assertIn("disable_egress", source)
        self.assertNotIn("163.204.223.16", source)

    def test_private_and_lan_ranges_stay_on_main_table(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for cidr in ("10.0.0.0/8", "100.64.0.0/10", "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16"):
            self.assertIn(cidr, source)
        self.assertIn('to 10.0.0.0/8 lookup main', source)
        self.assertIn('to 192.168.0.0/16 lookup main', source)
        self.assertIn('from "$subnet" iif "$wg_dev" lookup "$table"', source)
        self.assertIn('to fc00::/7 lookup main', source)
        self.assertIn('to fe80::/10 lookup main', source)

    def test_fw3_waits_for_xtables_lock_everywhere(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('XTABLES_WAIT_SECONDS="${REMOTE_GATE_XTABLES_WAIT_SECONDS:-15}"', source)
        self.assertIn('xtables4() { iptables -w "$XTABLES_WAIT_SECONDS" "$@"; }', source)
        self.assertIn('xtables6() { ip6tables -w "$XTABLES_WAIT_SECONDS" "$@"; }', source)
        self.assertIn('xtables4 -N "$FW3_FILTER_CHAIN"', source)
        self.assertIn('xtables4 -t nat -A "$FW3_NAT_CHAIN"', source)
        self.assertIn('xtables6 -t nat -L POSTROUTING', source)
        self.assertIn('xtables6 -N "$FW3_FILTER_CHAIN6"', source)
        self.assertIn('xtables4 -C FORWARD -j "$FW3_FILTER_CHAIN"', source)
        self.assertIn('xtables6 -C FORWARD -j "$FW3_FILTER_CHAIN6"', source)

    def test_remote_gate_input_firewall_is_not_reused_for_egress(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"$FIREWALL" detect', source)
        self.assertNotIn('"$FIREWALL" activate', source)
        self.assertNotIn('"$FIREWALL" clear', source)
        self.assertNotIn('"$FIREWALL" sync', source)
        self.assertIn("FW3_FILTER_CHAIN=\"WEIG_WG_EGRESS\"", source)
        self.assertIn('NFT_COMMENT="WeiG Remote Gate WG egress"', source)

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
