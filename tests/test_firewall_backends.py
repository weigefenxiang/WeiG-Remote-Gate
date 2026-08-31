import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIREWALL = ROOT / "openwrt/remote-gate-firewall.sh"
BACKENDS = ROOT / "openwrt/remote-gate-firewall-backends.sh"
VERIFY = ROOT / "openwrt/remote-gate-wireguard-verify.sh"
AGENT = ROOT / "openwrt/remote-gate-agent.sh"
INSTALL = ROOT / "openwrt/install.sh"
UPDATE = ROOT / "openwrt/update.sh"


def fake_cmd(directory: Path, name: str, body: str = "exit 0\n") -> None:
    path = directory / name
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class FirewallBackendTests(unittest.TestCase):
    def run_detect(self, names):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for name in names: fake_cmd(directory, name)
            env = os.environ.copy(); env["PATH"] = f"{directory}:/usr/bin:/bin"; env["REMOTE_GATE_LIB_DIR"] = str(ROOT / "openwrt")
            proc = subprocess.run(["/bin/sh", str(FIREWALL), "detect"], text=True, capture_output=True, env=env, check=False)
            return proc.returncode, proc.stdout.strip()

    def test_backend_detection_still_supports_fw4_and_fw3(self):
        self.assertEqual(self.run_detect(["fw4","nft","fw3","iptables","ipset"]), (0, "fw4-nftables"))
        self.assertEqual(self.run_detect(["fw3","iptables","ipset"]), (0, "fw3-iptables"))
        self.assertNotEqual(self.run_detect([])[0], 0)

    def test_modules_never_touch_forward_or_nat(self):
        source = "\n".join(path.read_text(encoding="utf-8") for path in (FIREWALL, BACKENDS, VERIFY))
        self.assertNotIn("FORWARD", source)
        self.assertNotIn("chain-pre/forward", source)
        self.assertNotIn("DNAT", source)
        self.assertNotIn("MASQUERADE", source)
        self.assertIn("INPUT", source)

    def test_candidate_and_discovery_windows_are_wireguard_udp_only(self):
        backends = BACKENDS.read_text(encoding="utf-8")
        verify = VERIFY.read_text(encoding="utf-8")
        self.assertIn("verification window", backends)
        self.assertIn("udp dport", backends)
        self.assertNotIn("authorized IPv4 ICMP", backends.split("IPv4 verification window", 1)[0])
        self.assertIn("VERIFY_CANDIDATE_SECONDS", FIREWALL.read_text(encoding="utf-8"))
        self.assertIn("VERIFY_DISCOVERY_SECONDS", FIREWALL.read_text(encoding="utf-8"))
        self.assertIn("verify_open any", verify)
        self.assertIn("multiple peers became active", verify)

    def test_final_authorization_is_wireguard_verified_and_family_independent(self):
        source = VERIFY.read_text(encoding="utf-8")
        firewall = FIREWALL.read_text(encoding="utf-8")
        self.assertIn("verify_wireguard_source", source)
        self.assertIn('rg_kind="wireguard_verified"', source)
        self.assertIn("AUTH_FILE_V4", firewall)
        self.assertIn("AUTH_FILE_V6", firewall)
        self.assertIn('clear_auth "${2:-all}"', firewall)

    def test_no_wan2_or_51820_hardcoding_in_new_firewall_modules(self):
        source = "\n".join(path.read_text(encoding="utf-8") for path in (FIREWALL, BACKENDS, VERIFY))
        self.assertNotIn("pppoe-WAN2", source)
        self.assertNotIn("51820", source)
        self.assertIn("wireguard_for_port", VERIFY.read_text(encoding="utf-8"))

    def test_openwrt_lifecycle_deploys_new_modules(self):
        for path in (INSTALL, UPDATE):
            source = path.read_text(encoding="utf-8")
            self.assertIn("remote-gate-firewall-backends.sh", source)
            self.assertIn("remote-gate-wireguard-verify.sh", source)
            self.assertIn("remote-gate-audit.sh", source)

    def test_agent_keeps_dynamic_multiwan_and_wireguard_discovery(self):
        source = AGENT.read_text(encoding="utf-8")
        self.assertIn("v4_protected_devices", source)
        self.assertIn("v6_protected_devices", source)
        self.assertIn("wireguard_ports", source)
        self.assertIn('"$FIREWALL" sync "$v4" "$v6" "$ports"', source)
        self.assertNotIn("pppoe-WAN2", source)
        self.assertNotIn("51820", source)

    def test_agent_drops_non_global_ipv6_before_inventory_upload(self):
        source = AGENT.read_text(encoding="utf-8")
        collect = source.split("collect_wans() {", 1)[1].split("wireguard_ports() {", 1)[0]
        self.assertIn("Internet Global Unicast lives in 2000::/3", source)
        self.assertIn("2*|3*", source)
        self.assertIn("jsonfilter -e '@[\"ipv6-address\"][*].address'", collect)
        self.assertIn('is_global_ipv6 "$address" && printf', collect)
        self.assertNotIn('jsonfilter -e \'@["ipv6-address"][*].address\' 2>/dev/null >> "$base.v6"', collect)

    def test_upgrade_keeps_ipv6_disabled_for_legacy_installations(self):
        self.assertIn("GATE_IPV6='auto'", INSTALL.read_text(encoding="utf-8"))
        update = UPDATE.read_text(encoding="utf-8")
        self.assertIn("append_default GATE_IPV6 disabled", update)
        self.assertNotIn("append_default GATE_IPV6 auto", update)


if __name__ == "__main__":
    unittest.main()
