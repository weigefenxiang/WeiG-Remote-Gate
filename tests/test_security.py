import unittest
from types import SimpleNamespace

from server.app.security import host_matches


class HostValidationTests(unittest.TestCase):
    def setUp(self):
        self.settings = SimpleNamespace(public_hostname="notify.weigshare.com")

    def test_accepts_public_hostname_and_loopback_hosts(self):
        self.assertTrue(host_matches(self.settings, "notify.weigshare.com"))
        self.assertTrue(host_matches(self.settings, "notify.weigshare.com:443"))
        self.assertTrue(host_matches(self.settings, "[::1]"))
        self.assertTrue(host_matches(self.settings, "[::1]:29444"))

    def test_rejects_ipv6_loopback_prefix_confusion(self):
        self.assertFalse(host_matches(self.settings, "[::1].example.com"))
        self.assertFalse(host_matches(self.settings, "[::1]evil"))
        self.assertFalse(host_matches(self.settings, "[::1]:invalid"))

    def test_rejects_other_hosts_and_ipv6_literals(self):
        self.assertFalse(host_matches(self.settings, "notify.weigshare.com.evil"))
        self.assertFalse(host_matches(self.settings, "[::2]"))
        self.assertFalse(host_matches(self.settings, None))


if __name__ == "__main__":
    unittest.main()
