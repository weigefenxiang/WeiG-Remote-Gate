from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "server/app/static"
TEMPLATE = ROOT / "server/app/templates/dashboard.html"
HOST = "127.0.0.1"
PORT = 8765


def fixture() -> dict:
    now = int(time.time())
    return {
        "schema": 2,
        "client_ip": "2408:8256:1970:66ae:1234:5678:90ab:cdef",
        "request_family": "ipv6",
        "client_sources": {
            "ipv4": {
                "address": "112.96.156.107",
                "observed_at": now - 80,
                "expires_at": now + 300,
                "source": "carrier_probe",
                "confidence": "candidate",
            },
            "ipv6": {
                "address": "2408:8256:1970:66ae:1234:5678:90ab:cdef",
                "observed_at": now,
                "expires_at": now + 300,
                "source": "carrier_probe",
                "confidence": "candidate",
            },
        },
        "csrf": "fixture-csrf",
        "inventory": {
            "schema": 2,
            "reported_at": now,
            "capabilities": {"gate_ipv4": True, "gate_ipv6": True, "natmap": False},
            "wans": [
                {
                    "name": "WAN2",
                    "device": "pppoe-WAN2",
                    "up": True,
                    "default_route_v4": True,
                    "default_route_v6": True,
                    "ipv4": [{"address": "203.0.113.18", "kind": "public"}],
                    "ipv6": [{"address": "2408:8256:1970:66ae:b8fd:db0b:8ae8:5b22", "kind": "global"}],
                },
                {
                    "name": "WAN",
                    "device": "pppoe-WAN",
                    "up": True,
                    "default_route_v4": True,
                    "default_route_v6": True,
                    "ipv4": [{"address": "172.20.111.32", "kind": "private"}],
                    "ipv6": [{"address": "2409:8a55:1905:702e:f193:310e:cf14:50f0", "kind": "global"}],
                },
            ],
            "natmap": [],
        },
        "endpoints": [
            {
                "id": "ep-wan2-v4",
                "wan": "WAN2",
                "device": "pppoe-WAN2",
                "family": "ipv4",
                "provider": "native",
                "external_address": "203.0.113.18",
                "external_port": 51820,
                "local_port": 51820,
                "wireguard": "WG_HOME",
                "reachability": "direct",
                "priority": 0,
            },
            {
                "id": "ep-wan2-v6",
                "wan": "WAN2",
                "device": "pppoe-WAN2",
                "family": "ipv6",
                "provider": "native",
                "external_address": "2408:8256:1970:66ae:b8fd:db0b:8ae8:5b22",
                "external_port": 51820,
                "local_port": 51820,
                "wireguard": "WG_HOME",
                "reachability": "direct",
                "priority": 10,
            },
            {
                "id": "ep-wan-v6",
                "wan": "WAN",
                "device": "pppoe-WAN",
                "family": "ipv6",
                "provider": "native",
                "external_address": "2409:8a55:1905:702e:f193:310e:cf14:50f0",
                "external_port": 51820,
                "local_port": 51820,
                "wireguard": "WG_HOME",
                "reachability": "direct",
                "priority": 10,
            },
        ],
        "current": {"schema": 1, "interfaces": {}},
        "agent": {
            "schema": 2,
            "reported_at": now,
            "fresh": True,
            "may_have_active_runtime": False,
            "wireguard": [{"name": "WG_HOME", "listen_port": 51820, "latest_handshake": now - 70, "rx": 1628, "tx": 1012}],
            "firewall": {
                "backend": "fw3-iptables",
                "ready": True,
                "active": False,
                "family": "",
                "scope": "",
                "source_ip": "",
                "device": "",
                "wg_port": 0,
                "expires_in": 0,
                "protected_devices_v4": 1,
                "protected_devices_v6": 2,
                "protected_ports": 1,
            },
            "transport": {"active_family": "ipv6", "active_device": "pppoe-WAN", "healthy": True, "last_ok_at": now},
        },
        "gate": {"queue": {"pending": None, "last": None}, "agent": {}},
        "activity": [
            {"at": now - 12, "type": "login_success", "source_ip": "2408:8256:1970:66ae:1234:5678:90ab:cdef"},
            {"at": now - 35, "type": "command_done", "action": "close", "detail": "authorization-cleared"},
            {"at": now - 60, "type": "gate_requested", "source_ip": "112.96.156.107", "wan": "WAN2", "wireguard": "WG_HOME", "family": "ipv4", "scope": "wg"},
        ],
        "server_time": now,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        pass

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/healthz":
            self._send(200, b"ok\n", "text/plain")
            return
        if path == "/":
            self._send(200, TEMPLATE.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/api/v1/dashboard":
            body = json.dumps(fixture(), separators=(",", ":")).encode()
            self._send(200, body, "application/json")
            return
        if path.startswith("/static/"):
            rel = path[len("/static/"):]
            target = (STATIC / rel).resolve()
            if STATIC.resolve() not in target.parents or not target.is_file():
                self._send(404, b"", "text/plain")
                return
            suffix = target.suffix
            content_type = {
                ".css": "text/css; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".ico": "image/x-icon",
            }.get(suffix, "application/octet-stream")
            self._send(200, target.read_bytes(), content_type)
            return
        self._send(404, b"", "text/plain")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length:
            self.rfile.read(length)
        if path == "/api/v1/gate/activate":
            self._send(202, b'{"command_id":"fixture","state":"pending"}', "application/json")
            return
        if path == "/api/v1/gate/close":
            self._send(202, b'{"command_id":"fixture-close","state":"pending"}', "application/json")
            return
        if path == "/logout":
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
            return
        self._send(404, b"", "text/plain")


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
