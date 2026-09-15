from __future__ import annotations

import base64
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from app.client_profiles import (  # noqa: E402
    EXPORTS,
    PUBLIC_TOKENS,
    accept_profile_result,
    consume_public_token,
    create_public_token,
    public_profile,
    queue_profile_create,
    queue_profile_revoke,
    render_flclash,
    render_format,
    render_netproxy_810,
    render_sing_box,
    render_wireguard,
)
from app.gate import GateError  # noqa: E402
from app.store import JsonStore  # noqa: E402


def key(byte: bytes) -> str:
    return base64.b64encode(byte * 32).decode("ascii")


def sample_profile() -> dict:
    return {
        "schema": 1,
        "id": "a" * 24,
        "name": "Pixel 10",
        "wireguard": "WG_HOME",
        "client_address": "10.66.66.4/32",
        "private_key": key(b"p"),
        "public_key": key(b"c"),
        "server_public_key": key(b"s"),
        "endpoint_family": "ipv4",
        "endpoint_address": "203.0.113.18",
        "endpoint_port": 51820,
        "access_method": "direct",
        "route_mode": "home",
        "home_networks": ["192.168.1.0/24", "10.66.66.0/24"],
        "dns": "192.168.1.1",
        "mtu": None,
        "persistent_keepalive": 25,
        "created_at": int(time.time()),
    }


class ClientProfilesTests(unittest.TestCase):
    def setUp(self):
        EXPORTS.clear()
        PUBLIC_TOKENS.clear()

    def test_public_projection_never_contains_client_private_key(self):
        public = public_profile(sample_profile(), export_available=True, export_expires_at=123)
        self.assertNotIn("private_key", public)
        self.assertTrue(public["export_available"])
        self.assertIn("netproxy-8.1.0", public["formats"])

    def test_wireguard_renderer_home_and_full_route_modes(self):
        profile = sample_profile()
        text = render_wireguard(profile)
        self.assertIn("PrivateKey = ", text)
        self.assertIn("Endpoint = 203.0.113.18:51820", text)
        self.assertIn("AllowedIPs = 192.168.1.0/24, 10.66.66.0/24", text)
        profile["route_mode"] = "full"
        self.assertIn("AllowedIPs = 0.0.0.0/0", render_wireguard(profile))

    def test_flclash_renderer_is_complete_mihomo_profile(self):
        text = render_flclash(sample_profile())
        self.assertIn("type: wireguard", text)
        self.assertIn("private-key:", text)
        self.assertIn("public-key:", text)
        self.assertIn("persistent-keepalive: 25", text)
        self.assertIn("IP-CIDR,192.168.1.0/24,RemoteGate,no-resolve", text)
        self.assertIn("MATCH,DIRECT", text)

    def test_netproxy_810_renderer_is_node_import_not_fake_routing_authority(self):
        text = render_netproxy_810(sample_profile())
        self.assertIn("NetProxy 8.1.0", text)
        self.assertIn("netproxyctl node import", text)
        self.assertIn("proxies:", text)
        self.assertIn("type: wireguard", text)
        self.assertNotIn("rules:", text)
        self.assertIn("select routing mode inside NetProxy", text)

    def test_sing_box_renderer_uses_modern_wireguard_endpoint(self):
        payload = json.loads(render_sing_box(sample_profile()))
        self.assertIn("endpoints", payload)
        self.assertNotIn("outbounds", payload)
        endpoint = payload["endpoints"][0]
        self.assertEqual(endpoint["type"], "wireguard")
        self.assertEqual(endpoint["peers"][0]["persistent_keepalive_interval"], 25)

    def test_profile_create_command_uses_authoritative_endpoint_and_shared_queue(self):
        with tempfile.TemporaryDirectory() as td:
            store = JsonStore(Path(td))
            endpoint = {
                "id": "ep_" + "1" * 20,
                "family": "ipv4",
                "access_method": "direct",
                "reachability": "direct",
                "service_type": "wireguard",
                "wireguard": "WG_HOME",
                "service_id": "wg.WG_HOME",
                "service_port": 51820,
                "external_port": 51820,
                "external_address": "203.0.113.18",
                "wan": "WAN2",
                "device": "pppoe-WAN2",
            }
            with patch("app.client_profiles.endpoint_by_id", return_value=endpoint):
                command = queue_profile_create(store, name="Pixel 10", endpoint_id=endpoint["id"], route_mode="home", persistent_keepalive=25)
            self.assertEqual(command["action"], "profile_create")
            self.assertEqual(command["wireguard"], "WG_HOME")
            self.assertEqual(store.read("commands.json", {})["pending"]["id"], command["id"])
            self.assertNotIn("source_ip", command)

    def test_result_is_memory_only_and_public_share_is_one_time(self):
        with tempfile.TemporaryDirectory() as td:
            store = JsonStore(Path(td))
            profile = sample_profile()
            command_id = "b" * 32
            store.write("commands.json", {"pending": {
                "id": command_id,
                "action": "profile_create",
                "profile_id": profile["id"],
                "profile_name": profile["name"],
                "wireguard": profile["wireguard"],
                "route_mode": profile["route_mode"],
                "persistent_keepalive": 25,
                "family": "ipv4",
                "access_method": "direct",
                "external_address": profile["endpoint_address"],
                "external_port": profile["endpoint_port"],
                "state": "pending",
            }, "next": [], "last": None})
            public = accept_profile_result(store, {"command_id": command_id, "profile": profile}, ttl_seconds=300)
            self.assertNotIn("private_key", public)
            self.assertNotIn(profile["private_key"], json.dumps(store.read("commands.json", {})))
            content_type, _, body = render_format(command_id, "wireguard")
            self.assertTrue(content_type.startswith("text/plain"))
            self.assertIn(profile["private_key"].encode(), body)
            shared = create_public_token(command_id, "flclash", ttl_seconds=300, public_base="https://notify.example.com")
            self.assertTrue(shared["url"].startswith("https://notify.example.com/p/"))
            consume_public_token(shared["token"])
            with self.assertRaises(GateError):
                consume_public_token(shared["token"])

    def test_revoke_command_uses_only_agent_reported_managed_profile(self):
        with tempfile.TemporaryDirectory() as td:
            store = JsonStore(Path(td))
            profile = public_profile(sample_profile())
            profile.pop("formats", None)
            profile.pop("export_available", None)
            profile.pop("export_expires_at", None)
            profile.pop("mapped_snapshot", None)
            store.write("agent-status.json", {"client_profiles": [profile]})
            command = queue_profile_revoke(store, profile["id"])
            self.assertEqual(command["action"], "profile_revoke")
            self.assertEqual(command["profile_id"], profile["id"])


if __name__ == "__main__":
    unittest.main()
