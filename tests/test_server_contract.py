import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "server/remote-gate.py"
CLIENT = ROOT / "server/app/client_sources.py"


class ServerContractTests(unittest.TestCase):
    def test_candidate_route_is_session_and_csrf_bound(self):
        source = RUNTIME.read_text(encoding="utf-8")
        block = source.split("def _candidate_post", 1)[1].split("def _activate_post", 1)[0]
        self.assertIn("self._require_session()", block)
        self.assertIn("self._require_csrf(session)", block)
        self.assertIn("observe_candidate", block)
        self.assertIn("invalid_source_candidate", block)

    def test_legacy_probe_is_gone_and_fail_closed(self):
        runtime = RUNTIME.read_text(encoding="utf-8")
        model = CLIENT.read_text(encoding="utf-8")
        self.assertIn('/api/v1/client-source/probe', runtime)
        self.assertIn("410", runtime)
        self.assertIn("legacy_source_probe_disabled", runtime)
        self.assertNotIn("issue_observer_token", runtime)
        self.assertNotIn("observer_hostnames", runtime)
        self.assertNotIn("redeem_observer_token", model)

    def test_csp_uses_ip_echo_only_as_connect_sources(self):
        source = RUNTIME.read_text(encoding="utf-8")
        self.assertIn("script-src 'self'; connect-src 'self' https://api.ipify.org https://api6.ipify.org", source)
        self.assertNotIn("script-src 'self' https://api.ipify.org", source)

    def test_dual_stack_activate_uses_independent_family_sources(self):
        source = RUNTIME.read_text(encoding="utf-8")
        self.assertIn("queue_activate_many", source)
        self.assertIn('families_raw = data.get("families")', source)
        self.assertIn('endpoint_ids = data.get("endpoint_ids")', source)
        self.assertIn("source_record_for_family", source)
        self.assertIn("source_confidence", source)

    def test_inventory_filters_non_global_ipv6_at_authoritative_boundary(self):
        source = RUNTIME.read_text(encoding="utf-8")
        self.assertIn("_sanitize_inventory", source)
        self.assertIn("address.is_global", source)
        self.assertIn("address.is_multicast", source)
        self.assertIn('ipaddress.ip_network("2000::/3")', source)
        self.assertIn("_sanitize_stored_inventory", source)
        self.assertIn('/api/v1/dashboard', source)

    def test_agent_status_preserves_both_family_authorizations(self):
        source = RUNTIME.read_text(encoding="utf-8")
        self.assertIn('"ipv4": _clean_fw_family', source)
        self.assertIn('"ipv6": _clean_fw_family', source)
        self.assertIn('"families": families', source)


if __name__ == "__main__":
    unittest.main()
