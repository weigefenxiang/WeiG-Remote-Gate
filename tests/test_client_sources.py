import hashlib
import tempfile
import unittest
from pathlib import Path

from server.app.client_sources import (
    issue_observer_token,
    observe_network_probe,
    observe_source,
    observer_hostnames,
    observer_url,
    redeem_observer_token,
    source_for_family,
    trusted_sources,
)
from server.app.store import JsonStore


class TrustedSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = JsonStore(Path(self.tmp.name))
        self.token = "session-token"
        self.secret = b"s" * 32
        self.session_id = hashlib.sha256(self.token.encode("ascii")).hexdigest()
        self.store.write("sessions.json", {self.session_id: {"expires_at": 1000, "created_at": 1}})

    def tearDown(self):
        self.tmp.cleanup()

    def test_ipv4_and_ipv6_can_be_observed_for_same_session(self):
        observe_source(self.store, self.token, "198.51.100.10", now=100)
        observe_source(self.store, self.token, "2001:4860:4860::8888", now=120)
        sources = trusted_sources(self.store, self.token, now=130)
        self.assertEqual(set(sources), {"ipv4", "ipv6"})

    def test_latest_cloudflare_observation_replaces_old_ipv4(self):
        observe_source(self.store, self.token, "198.51.100.10", now=100)
        observe_source(self.store, self.token, "203.0.113.20", now=110)
        self.assertEqual(source_for_family(self.store, self.token, "ipv4", now=111), "203.0.113.20")

    def test_observer_supplies_verified_ipv4_for_ipv6_first_session(self):
        observe_source(self.store, self.token, "2001:4860:4860::8888", now=100)
        token = issue_observer_token(self.token, "ipv4", self.secret, now=110)
        record = redeem_observer_token(
            self.store,
            token,
            "8.8.8.8",
            "v4.remote.example.com",
            "remote.example.com",
            self.secret,
            now=111,
        )
        sources = trusted_sources(self.store, self.token, now=112)
        self.assertEqual(record["family"], "ipv4")
        self.assertEqual(set(sources), {"ipv4", "ipv6"})
        self.assertEqual(sources["ipv4"]["address"], "8.8.8.8")
        self.assertEqual(sources["ipv4"]["source"], "cloudflare_observer")
        self.assertEqual(sources["ipv4"]["confidence"], "verified")

    def test_legacy_browser_reported_probe_is_disabled(self):
        with self.assertRaisesRegex(ValueError, "untrusted_source_probe_disabled"):
            observe_network_probe(self.store, self.token, "8.8.8.8", family="ipv4", now=100)

    def test_observer_hostnames_are_family_specific(self):
        self.assertEqual(
            observer_hostnames("Remote.Example.com."),
            {"ipv4": "v4.remote.example.com", "ipv6": "v6.remote.example.com"},
        )
        token = issue_observer_token(self.token, "ipv6", self.secret, now=100)
        self.assertTrue(observer_url("remote.example.com", "ipv6", token).startswith(
            "https://v6.remote.example.com/api/v1/client-source/observe?token="
        ))

    def test_observer_rejects_wrong_host(self):
        token = issue_observer_token(self.token, "ipv4", self.secret, now=100)
        with self.assertRaisesRegex(ValueError, "observer_host_mismatch"):
            redeem_observer_token(
                self.store, token, "8.8.8.8", "v6.remote.example.com",
                "remote.example.com", self.secret, now=101,
            )

    def test_observer_rejects_wrong_network_family(self):
        token = issue_observer_token(self.token, "ipv4", self.secret, now=100)
        with self.assertRaisesRegex(ValueError, "observer_family_mismatch"):
            redeem_observer_token(
                self.store, token, "2001:4860:4860::8888", "v4.remote.example.com",
                "remote.example.com", self.secret, now=101,
            )

    def test_observer_token_is_one_time(self):
        token = issue_observer_token(self.token, "ipv4", self.secret, now=100)
        args = (
            self.store, token, "8.8.8.8", "v4.remote.example.com",
            "remote.example.com", self.secret,
        )
        redeem_observer_token(*args, now=101)
        with self.assertRaisesRegex(ValueError, "observer_token_replayed"):
            redeem_observer_token(*args, now=102)

    def test_observer_token_expires(self):
        token = issue_observer_token(self.token, "ipv4", self.secret, now=100, ttl=30)
        with self.assertRaisesRegex(ValueError, "observer_token_expired"):
            redeem_observer_token(
                self.store, token, "8.8.8.8", "v4.remote.example.com",
                "remote.example.com", self.secret, now=131,
            )

    def test_observer_requires_live_login_session(self):
        token = issue_observer_token(self.token, "ipv4", self.secret, now=100)
        self.store.write("sessions.json", {})
        with self.assertRaisesRegex(ValueError, "observer_session_expired"):
            redeem_observer_token(
                self.store, token, "8.8.8.8", "v4.remote.example.com",
                "remote.example.com", self.secret, now=101,
            )

    def test_expired_family_cannot_be_selected(self):
        observe_source(self.store, self.token, "198.51.100.10", now=100)
        with self.assertRaisesRegex(ValueError, "client_source_not_observed"):
            source_for_family(self.store, self.token, "ipv4", now=1000)


if __name__ == "__main__":
    unittest.main()
