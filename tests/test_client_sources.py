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

    def test_verified_ipv4_and_ipv6_coexist(self):
        observe_source(self.store, self.token, "8.8.8.8", now=100)
        observe_source(self.store, self.token, "2001:4860:4860::8888", now=110)
        sources = trusted_sources(self.store, self.token, now=120)
        self.assertEqual(set(sources), {"ipv4", "ipv6"})
        self.assertEqual(sources["ipv4"]["confidence"], "verified")
        self.assertEqual(sources["ipv6"]["confidence"], "verified")

    def test_candidate_fills_missing_family(self):
        observe_source(self.store, self.token, "2001:4860:4860::8888", now=100)
        record = observe_candidate(self.store, self.token, "1.1.1.1", "ipv4", now=110)
        self.assertEqual(record["confidence"], "candidate")
        self.assertEqual(record["source"], "carrier_probe")
        self.assertEqual(source_for_family(self.store, self.token, "ipv4", now=111), "1.1.1.1")

    def test_candidate_does_not_replace_live_verified_source(self):
        observe_source(self.store, self.token, "8.8.8.8", now=100)
        record = observe_candidate(self.store, self.token, "1.1.1.1", "ipv4", now=110)
        self.assertEqual(record["address"], "8.8.8.8")
        self.assertEqual(source_record_for_family(self.store, self.token, "ipv4", now=111)["confidence"], "verified")

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
