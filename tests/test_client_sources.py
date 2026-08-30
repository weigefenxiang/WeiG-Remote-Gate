import tempfile
import unittest
from pathlib import Path

from server.app.client_sources import (
    observe_ipv4_probe,
    observe_network_probe,
    observe_source,
    source_for_family,
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

    def test_ipv4_and_ipv6_can_be_observed_for_same_session(self):
        observe_source(self.store, self.token, "198.51.100.10", now=100)
        observe_source(self.store, self.token, "2001:4860:4860::8888", now=120)
        sources = trusted_sources(self.store, self.token, now=130)
        self.assertEqual(set(sources), {"ipv4", "ipv6"})

    def test_latest_cgnat_egress_replaces_old_ipv4(self):
        observe_source(self.store, self.token, "198.51.100.10", now=100)
        observe_source(self.store, self.token, "203.0.113.20", now=110)
        self.assertEqual(source_for_family(self.store, self.token, "ipv4", now=111), "203.0.113.20")

    def test_carrier_probe_supplies_ipv4_for_ipv6_first_session(self):
        observe_source(self.store, self.token, "2001:4860:4860::8888", now=100)
        observe_ipv4_probe(self.store, self.token, "8.8.8.8", now=110)
        sources = trusted_sources(self.store, self.token, now=111)
        self.assertEqual(set(sources), {"ipv4", "ipv6"})
        self.assertEqual(sources["ipv4"]["address"], "8.8.8.8")
        self.assertEqual(sources["ipv4"]["source"], "carrier_probe")
        self.assertEqual(sources["ipv4"]["confidence"], "heuristic")
        self.assertEqual(source_for_family(self.store, self.token, "ipv4", now=111), "8.8.8.8")

    def test_ipv6_probe_complements_cloudflare_ipv4_without_deleting_it(self):
        observe_source(self.store, self.token, "1.1.1.1", now=100)
        observe_network_probe(self.store, self.token, "2001:4860:4860::8888", family="ipv6", now=110)
        sources = trusted_sources(self.store, self.token, now=111)
        self.assertEqual(set(sources), {"ipv4", "ipv6"})
        self.assertEqual(sources["ipv4"]["address"], "1.1.1.1")
        self.assertEqual(sources["ipv4"]["source"], "cloudflare")
        self.assertEqual(sources["ipv6"]["address"], "2001:4860:4860::8888")
        self.assertEqual(sources["ipv6"]["source"], "network_probe")

    def test_cloudflare_ipv4_replaces_carrier_probe(self):
        observe_ipv4_probe(self.store, self.token, "8.8.8.8", now=100)
        observe_source(self.store, self.token, "1.1.1.1", now=110)
        source = trusted_sources(self.store, self.token, now=111)["ipv4"]
        self.assertEqual(source["address"], "1.1.1.1")
        self.assertEqual(source["source"], "cloudflare")
        self.assertEqual(source["confidence"], "verified")

    def test_cloudflare_ipv6_replaces_network_probe(self):
        observe_network_probe(self.store, self.token, "2001:4860:4860::8888", family="ipv6", now=100)
        observe_source(self.store, self.token, "2606:4700:4700::1111", now=110)
        source = trusted_sources(self.store, self.token, now=111)["ipv6"]
        self.assertEqual(source["address"], "2606:4700:4700::1111")
        self.assertEqual(source["source"], "cloudflare")
        self.assertEqual(source["confidence"], "verified")

    def test_probe_never_overwrites_verified_same_family(self):
        observe_source(self.store, self.token, "1.1.1.1", now=100)
        result = observe_network_probe(self.store, self.token, "8.8.8.8", family="ipv4", now=110)
        self.assertEqual(result["address"], "1.1.1.1")
        self.assertEqual(result["source"], "cloudflare")

    def test_probe_rejects_private_ipv4(self):
        with self.assertRaisesRegex(ValueError, "global_ip_required"):
            observe_ipv4_probe(self.store, self.token, "100.64.1.2", now=100)

    def test_probe_rejects_family_mismatch(self):
        with self.assertRaisesRegex(ValueError, "probe_family_mismatch"):
            observe_network_probe(self.store, self.token, "8.8.8.8", family="ipv6", now=100)

    def test_expired_family_cannot_be_selected(self):
        observe_source(self.store, self.token, "198.51.100.10", now=100)
        with self.assertRaisesRegex(ValueError, "client_source_not_observed"):
            source_for_family(self.store, self.token, "ipv4", now=1000)


if __name__ == "__main__":
    unittest.main()
