import tempfile
import unittest
from pathlib import Path

from server.app.client_sources import (
    observe_candidate,
    observe_network_probe,
    observe_source,
    source_for_family,
    source_record_for_family,
    trusted_sources,
)
from server.app.store import JsonStore


class TrustedSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = JsonStore(Path(self.tmp.name))
        self.token = "session-token"

    def tearDown(self):
        self.tmp.cleanup()

    def test_http_observed_ipv4_and_ipv6_coexist(self):
        observe_source(self.store, self.token, "8.8.8.8", now=100)
        observe_source(self.store, self.token, "2001:4860:4860::8888", now=110)
        sources = trusted_sources(self.store, self.token, now=120)
        self.assertEqual(set(sources), {"ipv4", "ipv6"})
        self.assertEqual(sources["ipv4"]["confidence"], "observed")
        self.assertEqual(sources["ipv6"]["confidence"], "observed")

    def test_candidate_fills_missing_family(self):
        observe_source(self.store, self.token, "2001:4860:4860::8888", now=100)
        record = observe_candidate(self.store, self.token, "1.1.1.1", "ipv4", now=110)
        self.assertEqual(record["confidence"], "candidate")
        self.assertEqual(record["source"], "carrier_probe")
        self.assertEqual(source_for_family(self.store, self.token, "ipv4", now=111), "1.1.1.1")

    def test_candidate_cannot_replace_same_family_http_observation(self):
        observe_source(self.store, self.token, "8.8.8.8", now=100)
        record = observe_candidate(self.store, self.token, "1.1.1.1", "ipv4", now=110)
        self.assertEqual(record["address"], "8.8.8.8")
        self.assertEqual(record["confidence"], "observed")
        self.assertEqual(source_for_family(self.store, self.token, "ipv4", now=111), "8.8.8.8")

    def test_fresh_cloudflare_observation_replaces_same_family_candidate(self):
        record = observe_candidate(self.store, self.token, "1.1.1.1", "ipv4", now=100)
        self.assertEqual(record["address"], "1.1.1.1")
        self.assertEqual(record["confidence"], "candidate")

        refreshed = observe_source(self.store, self.token, "8.8.4.4", now=115)
        self.assertEqual(refreshed["address"], "8.8.4.4")
        self.assertEqual(refreshed["confidence"], "observed")
        selected = source_record_for_family(self.store, self.token, "ipv4", now=116)
        self.assertEqual(selected["address"], "8.8.4.4")
        self.assertEqual(selected["confidence"], "observed")

    def test_observing_one_family_does_not_delete_other_family_candidate(self):
        observe_candidate(self.store, self.token, "2001:4860:4860::8888", "ipv6", now=100)
        observe_source(self.store, self.token, "8.8.8.8", now=110)
        sources = trusted_sources(self.store, self.token, now=111)
        self.assertEqual(sources["ipv4"]["confidence"], "observed")
        self.assertEqual(sources["ipv6"]["confidence"], "candidate")

    def test_router_mapped_source_does_not_replace_remote_source(self):
        observe_source(self.store, self.token, "1.1.1.1", now=100)
        self.store.write(
            "inventory-v3.json",
            {
                "schema": 3,
                "wans": [],
                "mappings": [{"external_address": "8.8.4.4"}],
            },
        )
        record = observe_source(self.store, self.token, "8.8.4.4", now=110)
        self.assertEqual(record["address"], "1.1.1.1")
        self.assertEqual(source_for_family(self.store, self.token, "ipv4", now=111), "1.1.1.1")

    def test_router_egress_without_remote_source_is_suppressed(self):
        self.store.write(
            "wan-egress-v4.json",
            {"devices": {"pppoe-WAN": {"address": "8.8.4.4", "expires_at": 500}}},
        )
        record = observe_source(self.store, self.token, "8.8.4.4", now=100)
        self.assertEqual(record["confidence"], "suppressed")
        self.assertEqual(record["source"], "router_egress")
        self.assertEqual(trusted_sources(self.store, self.token, now=101), {})

    def test_active_gate_pins_authorized_source_past_source_ttl(self):
        observe_source(self.store, self.token, "1.1.1.1", now=100)
        self.store.write(
            "agent-status.json",
            {
                "firewall": {
                    "active": True,
                    "family": "ipv4",
                    "source_ip": "1.1.1.1",
                }
            },
        )
        record = observe_source(self.store, self.token, "8.8.8.8", now=1000)
        self.assertEqual(record["address"], "1.1.1.1")
        self.assertEqual(source_for_family(self.store, self.token, "ipv4", now=1000), "1.1.1.1")

    def test_dual_gate_pins_each_family_authorized_source(self):
        observe_source(self.store, self.token, "1.1.1.1", now=100)
        observe_source(self.store, self.token, "2001:4860:4860::8888", now=100)
        self.store.write(
            "agent-status.json",
            {
                "firewall": {
                    "active": True,
                    "family": "ipv4",
                    "source_ip": "1.1.1.1",
                    "families": {
                        "ipv4": {
                            "active": True,
                            "family": "ipv4",
                            "source_ip": "1.1.1.1",
                            "authorized_sources": ["1.1.1.1"],
                        },
                        "ipv6": {
                            "active": True,
                            "family": "ipv6",
                            "source_ip": "2001:4860:4860::8888",
                            "authorized_sources": ["2001:4860:4860::8888"],
                        },
                    },
                }
            },
        )

        ipv4 = observe_source(self.store, self.token, "8.8.8.8", now=1000)
        ipv6 = observe_source(self.store, self.token, "2606:4700:4700::1111", now=1000)
        self.assertEqual(ipv4["address"], "1.1.1.1")
        self.assertEqual(ipv6["address"], "2001:4860:4860::8888")
        sources = trusted_sources(self.store, self.token, now=1000)
        self.assertEqual(sources["ipv4"]["address"], "1.1.1.1")
        self.assertEqual(sources["ipv6"]["address"], "2001:4860:4860::8888")

    def test_family_status_pins_non_primary_authorized_source(self):
        observe_source(self.store, self.token, "8.8.8.8", now=100)
        self.store.write(
            "agent-status.json",
            {
                "firewall": {
                    "active": True,
                    "family": "ipv4",
                    "source_ip": "1.1.1.1",
                    "families": {
                        "ipv4": {
                            "active": True,
                            "family": "ipv4",
                            "source_ip": "1.1.1.1",
                            "authorized_sources": ["1.1.1.1", "8.8.8.8"],
                            "authorizations": [
                                {"source_ip": "1.1.1.1"},
                                {"source_ip": "8.8.8.8"},
                            ],
                        },
                        "ipv6": {"active": False, "authorized_sources": []},
                    },
                }
            },
        )

        record = observe_source(self.store, self.token, "9.9.9.9", now=1000)
        self.assertEqual(record["address"], "8.8.8.8")
        self.assertEqual(source_for_family(self.store, self.token, "ipv4", now=1000), "8.8.8.8")

    def test_non_public_or_special_addresses_are_rejected(self):
        for family, address in (
            ("ipv4", "10.0.0.1"),
            ("ipv4", "192.168.1.1"),
            ("ipv4", "127.0.0.1"),
            ("ipv6", "fe80::1"),
            ("ipv6", "fd00::1"),
            ("ipv6", "::1"),
            ("ipv6", "2001:db8::1"),
            ("ipv6", "ff02::1"),
        ):
            with self.subTest(address=address):
                with self.assertRaises(ValueError):
                    observe_candidate(self.store, self.token, address, family, now=100)

    def test_legacy_browser_probe_remains_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "legacy_source_probe_disabled"):
            observe_network_probe(self.store, self.token, "8.8.8.8", family="ipv4")

    def test_expired_candidate_is_not_selectable(self):
        observe_candidate(self.store, self.token, "1.1.1.1", "ipv4", now=100)
        with self.assertRaisesRegex(ValueError, "client_source_not_observed"):
            source_for_family(self.store, self.token, "ipv4", now=1000)


if __name__ == "__main__":
    unittest.main()
