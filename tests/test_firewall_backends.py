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
            for name in names:
                fake_cmd(directory, name)
            env = os.environ.copy()
            env["PATH"] = f"{directory}:/usr/bin:/bin"
            env["REMOTE_GATE_LIB_DIR"] = str(ROOT / "openwrt")
            proc = subprocess.run(
                ["/bin/sh", str(FIREWALL), "detect"],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            return proc.returncode, proc.stdout.strip()

    def test_backend_detection_still_supports_fw4_and_fw3(self):
        self.assertEqual(self.run_detect(["fw4", "nft", "fw3", "iptables", "ipset"]), (0, "fw4-nftables"))
        self.assertEqual(self.run_detect(["fw3", "iptables", "ipset"]), (0, "fw3-iptables"))
        self.assertNotEqual(self.run_detect([])[0], 0)

    def test_modules_never_touch_forward_or_nat(self):
        source = "\n".join(path.read_text(encoding="utf-8") for path in (FIREWALL, BACKENDS, VERIFY))
        self.assertNotIn("FORWARD", source)
        self.assertNotIn("chain-pre/forward", source)
        self.assertNotIn("DNAT", source)
        self.assertNotIn("MASQUERADE", source)
        self.assertIn("INPUT", source)

    def test_wireguard_verification_is_diagnostic_not_activation_gate(self):
        backends = BACKENDS.read_text(encoding="utf-8")
        verify = VERIFY.read_text(encoding="utf-8")
        firewall = FIREWALL.read_text(encoding="utf-8")
        agent = AGENT.read_text(encoding="utf-8")
        activate_block = verify.split("activate() {", 1)[1].split("verify_open() {", 1)[0]

        self.assertIn("verification window", backends)
        self.assertIn("verify_wireguard_source", verify)
        self.assertIn("verify-wireguard", firewall)
        self.assertNotIn("verify_wireguard_source", activate_block)
        self.assertIn("auth_record_file", activate_block)
        self.assertIn("authorization profile conflict", activate_block)
        self.assertIn('REMOTE_GATE_VERIFY_CANDIDATE_SECONDS="${REMOTE_GATE_VERIFY_CANDIDATE_SECONDS:-10}"', agent)
        self.assertIn('REMOTE_GATE_VERIFY_DISCOVERY_SECONDS="${REMOTE_GATE_VERIFY_DISCOVERY_SECONDS:-30}"', agent)

    def test_agent_returns_specific_firewall_failure_detail(self):
        source = AGENT.read_text(encoding="utf-8")
        self.assertIn('error_file="${TMP_BASE}.firewall-error"', source)
        self.assertIn('2>"$error_file"', source)
        self.assertIn("sed -n 's/^ERROR: //p'", source)
        self.assertIn('logger -t "$TAG" "activation failed: $detail"', source)
        self.assertIn('finish_activation_command "$id" false "$detail"', source)
        self.assertNotIn('ack "$id" false "firewall-activation-failed"', source)
        self.assertIn("sanitize_detail", source)

    def test_web_authorization_preserves_source_confidence(self):
        source = AGENT.read_text(encoding="utf-8")
        verify = VERIFY.read_text(encoding="utf-8")
        self.assertIn("source_confidence", source)
        self.assertIn("web_verified", source)
        self.assertIn("web_observed", source)
        self.assertIn("web_candidate", source)
        self.assertIn("valid_source_kind", FIREWALL.read_text(encoding="utf-8"))
        self.assertIn("web authorization active", verify)

    def test_authorization_state_supports_multiple_sources_per_family(self):
        firewall = FIREWALL.read_text(encoding="utf-8")
        backends = BACKENDS.read_text(encoding="utf-8")
        verify = VERIFY.read_text(encoding="utf-8")
        self.assertIn("AUTH_DIR_V4", firewall)
        self.assertIn("AUTH_DIR_V6", firewall)
        self.assertIn("authorization-ipv4.d", firewall)
        self.assertIn("authorization-ipv6.d", firewall)
        self.assertIn("read_auth_records", backends)
        self.assertIn("authorized_sources", verify)
        self.assertIn("authorizations", verify)
        self.assertIn("source_count", verify)
        self.assertIn('clear_auth "${2:-all}"', firewall)

    def test_close_clears_gate_authorizations_without_stopping_mapping(self):
        source = AGENT.read_text(encoding="utf-8")
        close_block = source.split("        close)\n", 1)[1].split("            ;;", 1)[0]
        self.assertIn('"$FIREWALL" clear', close_block)
        self.assertIn('"$EGRESS" disable', close_block)
        self.assertNotIn('"$MAPPING"', close_block)
        self.assertNotIn("stop", close_block)
        self.assertIn("all-authorizations-and-egress-cleared", close_block)

    def test_authorization_ttl_is_enforced_by_kernel_sets(self):
        backends = BACKENDS.read_text(encoding="utf-8")
        self.assertIn('ipset -exist add "$rg_set" "$rg_ip" timeout "$rg_remaining"', backends)
        self.assertIn("set weig_remote_gate_auth_ipv4 { type ipv4_addr; flags timeout; }", backends)
        self.assertIn("set weig_remote_gate_auth_ipv6 { type ipv6_addr; flags timeout; }", backends)
        self.assertIn("add element inet fw4 $rg_auth_set { $rg_ip timeout ${rg_remaining}s }", backends)
        self.assertIn('[ "$rg_expires" -gt "$rg_now" ]', backends)

    def test_concurrent_sources_share_one_safe_family_profile(self):
        source = VERIFY.read_text(encoding="utf-8")
        backends = BACKENDS.read_text(encoding="utf-8")
        self.assertIn("authorization profile conflict", source)
        self.assertIn("concurrent authorization profile differed", backends)
        self.assertIn('rg_existing_dev="$2"', source)
        self.assertIn('rg_existing_port="$3"', source)
        self.assertIn('rg_existing_scope="${rg_existing_meta%%:*}"', source)

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
        self.assertIn('wg_ports="$(wireguard_ports', source)
        self.assertIn('mapped_pairs="$(mapped_ingress_pairs', source)
        self.assertIn('"$FIREWALL" sync "$v4" "$v6" "$wg_ports" "$mapped_pairs"', source)
        self.assertNotIn("pppoe-WAN2", source)
        self.assertNotIn("51820", source)

    def test_agent_drops_non_global_ipv6_before_inventory_upload(self):
        source = AGENT.read_text(encoding="utf-8")
        collect = source.split("collect_wans() {", 1)[1].split("wireguard_ports() {", 1)[0]
        self.assertIn("is_global_ipv6()", source)
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
