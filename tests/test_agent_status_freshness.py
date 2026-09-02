import unittest
from pathlib import Path

from server.app.client_sources import (
    AGENT_STATUS_FRESH_SECONDS,
    agent_status_is_fresh,
    fail_closed_agent_status,
)

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server/remote-gate.py"


class AgentStatusFreshnessTests(unittest.TestCase):
    def sample(self, reported_at=1000):
        return {
            "schema": 3,
            "reported_at": reported_at,
            "wireguard": [{"name": "WG_HOME", "listen_port": 51820}],
            "firewall": {
                "backend": "fw3-iptables",
                "ready": True,
                "ipv6_capable": True,
                "active": True,
                "family": "ipv4",
                "scope": "wg",
                "expires_in": 300,
                "source_ip": "1.1.1.1",
                "device": "pppoe-WAN",
                "wg_port": 51820,
                "ingress_port": 54321,
                "families": {
                    "ipv4": {
                        "active": True,
                        "authorized_sources": ["1.1.1.1"],
                        "authorizations": [{"source_ip": "1.1.1.1", "expires_in": 300}],
                    }
                },
                "protected_devices_v4": 1,
                "protected_devices_v6": 0,
                "protected_ports": 1,
            },
            "egress": {
                "active": True,
                "state": "active",
                "mode": "ipv4",
                "wan": "WAN2",
                "wan_v4": "WAN2",
                "wg": "WG_HOME",
                "expires_in": 300,
            },
            "mapping": {"available": True, "state": "active", "active_mappings": 1},
            "transport": {
                "active_family": "ipv4",
                "active_device": "pppoe-WAN2",
                "healthy": True,
                "last_ok_at": 1000,
            },
        }

    def test_fresh_report_remains_authoritative(self):
        status = self.sample()
        self.assertTrue(agent_status_is_fresh(status, now=1000 + AGENT_STATUS_FRESH_SECONDS))
        view = fail_closed_agent_status(status, now=1000 + AGENT_STATUS_FRESH_SECONDS)
        self.assertTrue(view["fresh"])
        self.assertTrue(view["firewall"]["active"])
        self.assertTrue(view["egress"]["active"])
        self.assertEqual(view["wireguard"][0]["name"], "WG_HOME")
        self.assertTrue(view["transport"]["healthy"])

    def test_stale_report_loses_all_runtime_authority(self):
        status = self.sample()
        view = fail_closed_agent_status(status, now=1001 + AGENT_STATUS_FRESH_SECONDS)
        self.assertFalse(view["fresh"])
        self.assertEqual(view["reported_at"], 1000)
        self.assertEqual(view["firewall"]["backend"], "fw3-iptables")
        self.assertFalse(view["firewall"]["ready"])
        self.assertFalse(view["firewall"]["active"])
        self.assertFalse(view["firewall"]["families"]["ipv4"]["active"])
        self.assertEqual(view["firewall"]["families"]["ipv4"]["authorized_sources"], [])
        self.assertEqual(view["wireguard"], [])
        self.assertFalse(view["egress"]["active"])
        self.assertEqual(view["egress"]["state"], "inactive")
        self.assertFalse(view["mapping"]["available"])
        self.assertEqual(view["mapping"]["state"], "unavailable")
        self.assertFalse(view["transport"]["healthy"])
        self.assertEqual(view["transport"]["active_family"], "")
        self.assertEqual(view["transport"]["active_device"], "")

    def test_future_report_outside_skew_window_is_not_authoritative(self):
        status = self.sample(reported_at=2000)
        self.assertFalse(agent_status_is_fresh(status, now=1000))
        self.assertFalse(fail_closed_agent_status(status, now=1000)["fresh"])

    def test_dashboard_sanitizes_agent_before_base_handler_renders(self):
        source = SERVER.read_text(encoding="utf-8")
        self.assertIn("fail_closed_agent_status", source)
        self.assertIn("_sanitize_stored_agent_status()", source)
        dashboard = source.split("def do_GET(self) -> None:", 1)[1].split("super().do_GET()", 1)[0]
        self.assertLess(dashboard.index("_sanitize_stored_agent_status()"), len(dashboard))


if __name__ == "__main__":
    unittest.main()
