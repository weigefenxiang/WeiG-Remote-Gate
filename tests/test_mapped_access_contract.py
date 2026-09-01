from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
AGENT = (ROOT / "openwrt" / "remote-gate-agent.sh").read_text(encoding="utf-8")
FIREWALL = (ROOT / "openwrt" / "remote-gate-firewall.sh").read_text(encoding="utf-8")
BACKENDS = (ROOT / "openwrt" / "remote-gate-firewall-backends.sh").read_text(encoding="utf-8")
MAPPING = (ROOT / "openwrt" / "remote-gate-mapping.sh").read_text(encoding="utf-8")
REGISTRY = (ROOT / "openwrt" / "remote-gate-service-registry.sh").read_text(encoding="utf-8")
APP = (ROOT / "server" / "app" / "static" / "js" / "app.js").read_text(encoding="utf-8")
MAPPER = (ROOT / "native" / "remote-gate-mapper.c").read_text(encoding="utf-8")


class MappedAccessContractTests(unittest.TestCase):
    def test_agent_keeps_wireguard_ports_and_mapped_pairs_separate(self):
        self.assertIn('wg_ports="$(wireguard_ports', AGENT)
        self.assertIn('mapped_pairs="$(mapped_ingress_pairs', AGENT)
        self.assertIn('sync "$v4" "$v6" "$wg_ports" "$mapped_pairs"', AGENT)
        self.assertNotIn('registered_ingress_ports()', AGENT)

    def test_firewall_authorizes_only_current_registered_ingress(self):
        self.assertIn('MAPPED_INGRESS_V4_FILE=', FIREWALL)
        self.assertIn('protected_ingress_current()', FIREWALL)
        self.assertIn('"${rg_dev}|${rg_port}"', FIREWALL)

    def test_fw4_uses_device_port_tuple_for_mapped_ingress(self):
        self.assertIn('type ifname . inet_service', BACKENDS)
        self.assertIn('iifname . udp dport @weig_remote_gate_mapped_ingress_v4', BACKENDS)
        self.assertIn('"$rg_dev" . $rg_port', BACKENDS)

    def test_fw3_uses_exact_device_and_port_drop(self):
        self.assertIn('fw3_load_mapped_drops_v4()', BACKENDS)
        self.assertIn('-i "$rg_dev" -p udp --dport "$rg_port" -j DROP', BACKENDS)

    def test_mapper_waits_for_firewall_go_signal(self):
        self.assertIn('--go-file', MAPPING)
        self.assertIn('activate-prepared', MAPPING)
        self.assertIn('go_file', MAPPER)
        self.assertIn('wait_for_go', MAPPER)

    def test_service_registry_is_the_only_service_authority(self):
        self.assertIn('validate)', REGISTRY)
        self.assertIn('"$SERVICES" validate', MAPPING)
        self.assertIn('service-not-registered', AGENT)
        self.assertIn('service-wireguard-mismatch', AGENT)

    def test_ui_uses_access_method_not_natmap_branding(self):
        self.assertIn("item.access_method === 'mapped'", APP)
        self.assertIn("method = 'Mapped'", APP)
        self.assertNotIn("provider === 'natmap'", APP)
        self.assertNotIn("provider = 'NATMap'", APP)


if __name__ == "__main__":
    unittest.main()
