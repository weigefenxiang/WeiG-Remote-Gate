import tempfile
import unittest
from pathlib import Path

from server.app.client_sources import observe_source, source_for_family, trusted_sources
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

    def test_expired_family_cannot_be_selected(self):
        observe_source(self.store, self.token, "198.51.100.10", now=100)
        with self.assertRaisesRegex(ValueError, "client_source_not_observed"):
            source_for_family(self.store, self.token, "ipv4", now=1000)


if __name__ == "__main__":
    unittest.main()
