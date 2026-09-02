import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = (ROOT / "openwrt/remote-gate-service-registry.sh").read_text(encoding="utf-8")
AGENT = (ROOT / "openwrt/remote-gate-agent.sh").read_text(encoding="utf-8")
MAPPING = (ROOT / "openwrt/remote-gate-mapping.sh").read_text(encoding="utf-8")


class DynamicServicePortContractTests(unittest.TestCase):
    def test_service_registry_discovers_current_wireguard_listener(self):
        self.assertIn('wg show "$name" listen-port', REGISTRY)
        self.assertIn('"service_port":%s', REGISTRY)
        self.assertIn('validate <service-id> <transport> <service-port>', REGISTRY)

    def test_agent_revalidates_command_service_port_against_registry(self):
        self.assertIn('service_port="$(jsonfilter -i "$BODY" -e \'@.service_port\'', AGENT)
        self.assertIn('[ -n "$service_port" ] || service_port="$legacy_wg_port"', AGENT)
        self.assertIn('"$SERVICES" validate "$service_id" udp "$service_port"', AGENT)
        self.assertIn('[ "$ingress_port" = "$service_port" ]', AGENT)

    def test_mapping_passes_dynamic_service_port_to_mapper(self):
        self.assertIn('ENTRY_SERVICE_PORT="$4"', MAPPING)
        self.assertIn('"$SERVICES" validate "$ENTRY_SERVICE_ID" udp "$ENTRY_SERVICE_PORT"', MAPPING)
        self.assertIn('--service-port "$service_port"', MAPPING)

    def test_core_runtime_does_not_hardcode_default_wireguard_port(self):
        for name, source in (("registry", REGISTRY), ("agent", AGENT), ("mapping", MAPPING)):
            self.assertNotIn("51820", source, f"{name} must not hardcode the current-device WireGuard port")


if __name__ == "__main__":
    unittest.main()
