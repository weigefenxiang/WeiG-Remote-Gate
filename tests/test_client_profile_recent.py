from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from app.client_profiles import (  # noqa: E402
    EXPORTS,
    EXPORT_OWNERS,
    PUBLIC_TOKENS,
    accept_profile_result,
    profile_command_owned,
    profile_history,
    queue_profile_create,
    recent_results,
    render_format,
    result_view,
)
from app.gate import GateError  # noqa: E402
from app.store import JsonStore  # noqa: E402


def key(byte: bytes) -> str:
    return base64.b64encode(byte * 32).decode("ascii")


def endpoint() -> dict:
    return {
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


def result_profile(command: dict) -> dict:
    return {
        "schema": 1,
        "id": command["profile_id"],
        "name": command["profile_name"],
        "wireguard": command["wireguard"],
        "client_address": "10.77.0.3/32",
        "private_key": key(b"p"),
        "public_key": key(b"c"),
        "server_public_key": key(b"s"),
        "endpoint_address": command["external_address"],
        "endpoint_port": command["external_port"],
        "route_mode": command["route_mode"],
        "home_networks": ["192.168.1.0/24", "10.77.0.0/24"],
        "dns": "192.168.1.1",
        "mtu": None,
        "persistent_keepalive": command["persistent_keepalive"],
        "created_at": command["created_at"],
    }


class ClientProfileRecentResultsTests(unittest.TestCase):
    def setUp(self):
        EXPORTS.clear()
        EXPORT_OWNERS.clear()
        PUBLIC_TOKENS.clear()

    def test_recent_export_is_owned_by_requesting_session_only(self):
        with tempfile.TemporaryDirectory() as td:
            store = JsonStore(Path(td))
            owner = "a" * 64
            other = "b" * 64
            with patch("app.client_profiles.endpoint_by_id", return_value=endpoint()):
                command = queue_profile_create(
                    store,
                    name="Pixel 10",
                    endpoint_id=endpoint()["id"],
                    route_mode="home",
                    persistent_keepalive=25,
                    owner_key=owner,
                )
            self.assertTrue(profile_command_owned(command["id"], owner))
            self.assertFalse(profile_command_owned(command["id"], other))

            public = accept_profile_result(
                store,
                {"command_id": command["id"], "profile": result_profile(command)},
                ttl_seconds=300,
            )
            self.assertTrue(public["export_available"])
            self.assertEqual(len(recent_results(owner)), 1)
            self.assertEqual(recent_results(other), [])
            self.assertEqual(recent_results(owner)[0]["command_id"], command["id"])

            with self.assertRaises(GateError):
                result_view(command["id"], other)
            with self.assertRaises(GateError):
                render_format(command["id"], "wireguard", other)
            _, _, body = render_format(command["id"], "wireguard", owner)
            self.assertIn(result_profile(command)["private_key"].encode(), body)

    def test_persistent_history_contains_no_export_secret_or_command_id(self):
        with tempfile.TemporaryDirectory() as td:
            store = JsonStore(Path(td))
            owner = "c" * 64
            with patch("app.client_profiles.endpoint_by_id", return_value=endpoint()):
                command = queue_profile_create(
                    store,
                    name="RG-HW-Test",
                    endpoint_id=endpoint()["id"],
                    owner_key=owner,
                )
            profile = result_profile(command)
            accept_profile_result(store, {"command_id": command["id"], "profile": profile}, ttl_seconds=300)

            raw = store.read("client-profile-history.json", [])
            serialized = json.dumps(raw)
            self.assertNotIn(profile["private_key"], serialized)
            self.assertNotIn(command["id"], serialized)
            self.assertNotIn("private_key", serialized)
            self.assertEqual(profile_history(store)[0]["profile_id"], command["profile_id"])

    def test_ui_has_recent_results_and_viewport_level_mobile_qr(self):
        entry = (ROOT / "server" / "profile-entry.py").read_text(encoding="utf-8")
        self.assertIn("/api/v1/client-profiles/recent", entry)
        self.assertIn('id="profile-recent-button"', entry)
        self.assertIn('id="profile-qr-layer"', entry)
        self.assertIn("100dvh", entry)
        self.assertIn("max-height:min(68dvh,440px)", entry)
        self.assertNotIn("localStorage", entry)
        self.assertNotIn("sessionStorage", entry)


if __name__ == "__main__":
    unittest.main()
