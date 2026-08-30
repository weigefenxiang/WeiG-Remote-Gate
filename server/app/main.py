from __future__ import annotations

import html
import ipaddress
import json
import mimetypes
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .client_sources import delete_sources, observe_network_probe, observe_source, source_for_family, trusted_sources
from .config import load_settings
from .endpoints import build_endpoints, normalize_inventory, observe_wan_egress, validate_inventory_v2
from .gate import GateError, ack_command, gate_view, pull_command, queue_activate, queue_close
from .security import (
    bearer_matches,
    clear_session_cookie,
    client_ip,
    create_session,
    delete_session,
    host_matches,
    is_private_wan_ipv4,
    parse_session,
    session_cookie,
    verify_password,
)
from .store import JsonStore


SETTINGS = load_settings()
STORE = JsonStore(SETTINGS.state_dir)
PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"
TEMPLATE_DIR = PACKAGE_DIR / "templates"

MAX_BODY = 32 * 1024
NAME_RE = re.compile(r"^[A-Za-z0-9_.:@-]{1,64}$")
DEVICE_RE = re.compile(r"^[A-Za-z0-9_.:@+-]{1,128}$")
ENDPOINT_RE = re.compile(r"^ep_[a-f0-9]{20}$")

LOGIN_LOCK = threading.RLock()
LOGIN_FAILURES: dict[str, list[float]] = {}
LOGIN_BLOCKED_UNTIL: dict[str, float] = {}
LOGIN_WINDOW = 10 * 60
LOGIN_MAX_FAILURES = 5
LOGIN_BLOCK_SECONDS = 10 * 60


def _safe_name(value: object) -> str:
    text = str(value or "").strip()
    if not NAME_RE.fullmatch(text):
        raise ValueError("invalid_name")
    return text


def _safe_device(value: object) -> str:
    text = str(value or "").strip()
    if not DEVICE_RE.fullmatch(text):
        raise ValueError("invalid_device")
    return text


def _safe_endpoint_id(value: object) -> str:
    text = str(value or "").strip()
    if not ENDPOINT_RE.fullmatch(text):
        raise ValueError("invalid_endpoint")
    return text


def _safe_ipv4(value: object) -> str:
    address = ipaddress.ip_address(str(value or "").strip())
    if address.version != 4:
        raise ValueError("ipv4_required")
    return str(address)


def _safe_probe_address(value: object, family: str) -> str:
    if family not in {"ipv4", "ipv6"}:
        raise ValueError("invalid_family")
    address = ipaddress.ip_address(str(value or "").strip())
    expected = 4 if family == "ipv4" else 6
    if address.version != expected or not address.is_global:
        raise ValueError("invalid_probe_address")
    return str(address)


def _login_blocked(ip: str) -> bool:
    now = time.time()
    with LOGIN_LOCK:
        until = LOGIN_BLOCKED_UNTIL.get(ip, 0)
        if until > now:
            return True
        LOGIN_BLOCKED_UNTIL.pop(ip, None)
        failures = [x for x in LOGIN_FAILURES.get(ip, []) if x > now - LOGIN_WINDOW]
        LOGIN_FAILURES[ip] = failures
        return len(failures) >= LOGIN_MAX_FAILURES


def _login_failed(ip: str) -> None:
    now = time.time()
    with LOGIN_LOCK:
        failures = [x for x in LOGIN_FAILURES.get(ip, []) if x > now - LOGIN_WINDOW]
        failures.append(now)
        LOGIN_FAILURES[ip] = failures
        if len(failures) >= LOGIN_MAX_FAILURES:
            LOGIN_BLOCKED_UNTIL[ip] = now + LOGIN_BLOCK_SECONDS


def _login_succeeded(ip: str) -> None:
    with LOGIN_LOCK:
        LOGIN_FAILURES.pop(ip, None)
        LOGIN_BLOCKED_UNTIL.pop(ip, None)


def _request_family(source: str) -> str:
    return "ipv4" if ipaddress.ip_address(source).version == 4 else "ipv6"


class Handler(BaseHTTPRequestHandler):
    server_version = "WeiG-Remote-Gate"
    sys_version = ""

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.log_date_time_string()} {self.client_address[0]} {fmt % args}")

    def _send_headers(self, status: int, content_type: str, length: int | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self' https://api.ipify.org https://api6.ipify.org; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
        )

    def _bytes(self, status: int, body: bytes, content_type: str) -> None:
        self._send_headers(status, content_type, len(body))
        self.end_headers()
        self.wfile.write(body)

    def _text(self, status: int, body: str, content_type: str = "text/plain; charset=utf-8") -> None:
        self._bytes(status, body.encode("utf-8"), content_type)

    def _json(self, status: int, value: object) -> None:
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._bytes(status, body, "application/json; charset=utf-8")

    def _empty(self, status: int) -> None:
        self._send_headers(status, "text/plain; charset=utf-8", 0)
        self.end_headers()

    def _read_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid_content_length") from exc
        if length < 0 or length > MAX_BODY:
            raise ValueError("body_too_large")
        return self.rfile.read(length)

    def _read_json(self) -> dict:
        raw = self._read_body()
        try:
            value = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid_json") from exc
        if not isinstance(value, dict):
            raise ValueError("json_object_required")
        return value

    def _session(self):
        return parse_session(SETTINGS, STORE, self.headers.get("Cookie"))

    def _require_session(self):
        session = self._session()
        if not session:
            self._json(401, {"error": "unauthorized"})
            return None
        return session

    def _require_csrf(self, session) -> bool:
        supplied = self.headers.get("X-CSRF-Token", "")
        if not supplied or supplied != session.csrf:
            self._json(403, {"error": "csrf"})
            return False
        return True

    def _require_agent(self) -> bool:
        if not bearer_matches(SETTINGS, self.headers.get("Authorization")):
            self._json(401, {"error": "unauthorized"})
            return False
        return True

    def _trusted_client_ip(self) -> str | None:
        return client_ip(self.headers)

    def _template(self, name: str, replacements: dict[str, str] | None = None) -> str:
        value = (TEMPLATE_DIR / name).read_text(encoding="utf-8")
        for key, replacement in (replacements or {}).items():
            value = value.replace("{{" + key + "}}", html.escape(replacement))
        return value

    def _serve_static(self, path: str) -> bool:
        if not path.startswith("/static/"):
            return False
        relative = path[len("/static/"):]
        if ".." in relative.split("/"):
            self._empty(404)
            return True
        file_path = STATIC_DIR / relative
        if not file_path.is_file():
            self._empty(404)
            return True
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        body = file_path.read_bytes()
        self._send_headers(200, content_type, len(body))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(body)
        return True

    def _host_ok(self) -> bool:
        if host_matches(SETTINGS, self.headers.get("Host")):
            return True
        self._json(421, {"error": "invalid_host"})
        return False

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/healthz":
            self._text(200, "ok\n")
            return

        if not self._host_ok():
            return

        if self._serve_static(path):
            return

        if path == "/":
            if self._session():
                self._text(200, self._template("dashboard.html"), "text/html; charset=utf-8")
            else:
                self._text(200, self._template("login.html", {"ERROR": ""}), "text/html; charset=utf-8")
            return

        if path == "/api/v1/dashboard":
            session = self._require_session()
            if not session:
                return
            source = self._trusted_client_ip()
            if not source:
                self._json(400, {"error": "missing_cf_connecting_ip"})
                return
            observe_source(STORE, session.token, source)
            current = STORE.read("current.json", {"schema": 1, "interfaces": {}})
            inventory = normalize_inventory(STORE)
            endpoints = build_endpoints(STORE)
            agent = STORE.read("agent-status.json", {})
            activity = STORE.read("activity.json", [])
            gate = gate_view(STORE)
            self._json(
                200,
                {
                    "schema": 2,
                    "client_ip": source,
                    "request_family": _request_family(source),
                    "client_sources": trusted_sources(STORE, session.token),
                    "csrf": session.csrf,
                    "current": current,
                    "inventory": inventory,
                    "endpoints": endpoints,
                    "agent": agent,
                    "gate": gate,
                    "activity": activity[-30:] if isinstance(activity, list) else [],
                    "server_time": int(time.time()),
                },
            )
            return

        if path == "/api/v1/agent/pull":
            if not self._require_agent():
                return
            command = pull_command(STORE)
            if command is None:
                self._empty(204)
            else:
                self._json(200, command)
            return

        self._empty(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        if not self._host_ok():
            return

        if path == "/login":
            source = self._trusted_client_ip()
            if not source:
                self._text(400, self._template("login.html", {"ERROR": "Cloudflare client IP is missing."}), "text/html; charset=utf-8")
                return
            if _login_blocked(source):
                self._text(429, self._template("login.html", {"ERROR": "Too many failed attempts. Try again later."}), "text/html; charset=utf-8")
                return
            try:
                form = parse_qs(self._read_body().decode("utf-8"), keep_blank_values=True)
            except (ValueError, UnicodeDecodeError):
                self._empty(400)
                return
            username = (form.get("username") or [""])[0]
            password = (form.get("password") or [""])[0]
            remember = (form.get("remember") or [""])[0] == "1"
            if username != SETTINGS.username or not verify_password(SETTINGS, password):
                _login_failed(source)
                STORE.append_activity({"type": "login_failed", "source_ip": source})
                self._text(401, self._template("login.html", {"ERROR": "Invalid username or password."}), "text/html; charset=utf-8")
                return
            _login_succeeded(source)
            session = create_session(SETTINGS, STORE, remember)
            observe_source(STORE, session.token, source)
            STORE.append_activity({"type": "login_success", "source_ip": source})
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", session_cookie(session.token, session.expires_at))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return

        if path == "/logout":
            session = self._require_session()
            if not session or not self._require_csrf(session):
                return
            delete_sources(STORE, session.token)
            delete_session(STORE, session.token)
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", clear_session_cookie())
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return

        if path == "/api/v1/client-source/probe":
            session = self._require_session()
            if not session or not self._require_csrf(session):
                return
            try:
                data = self._read_json()
                if data.get("family"):
                    family = str(data.get("family") or "").strip()
                    address = _safe_probe_address(data.get("address"), family)
                else:
                    family = "ipv4"
                    address = _safe_probe_address(data.get("ipv4"), family)
                record = observe_network_probe(STORE, session.token, address, family=family)
            except (ValueError, TypeError):
                self._json(400, {"error": "invalid_source_probe"})
                return
            self._json(200, record)
            return

        if path == "/api/v1/agent/egress-probe":
            if not self._require_agent():
                return
            source = self._trusted_client_ip()
            try:
                address = ipaddress.ip_address(str(source or ""))
                if address.version != 4 or not address.is_global:
                    raise ValueError("public_ipv4_required")
                query = parse_qs(urlparse(self.path).query)
                device = _safe_device((query.get("device") or [""])[0])
                observe_wan_egress(STORE, device, str(address))
            except ValueError:
                self._json(400, {"error": "invalid_egress_probe"})
                return
            self._empty(204)
            return

        if path == "/api/v1/gate/activate":
            session = self._require_session()
            if not session or not self._require_csrf(session):
                return
            current_source = self._trusted_client_ip()
            if not current_source:
                self._json(400, {"error": "missing_cf_connecting_ip"})
                return
            observe_source(STORE, session.token, current_source)
            try:
                data = self._read_json()
                endpoint_raw = data.get("endpoint_id")
                if endpoint_raw:
                    family = str(data.get("family") or "").strip()
                    selected_source = source_for_family(STORE, session.token, family)
                    command = queue_activate(
                        STORE,
                        source_ip=selected_source,
                        endpoint_id=_safe_endpoint_id(endpoint_raw),
                        family=family,
                        scope=str(data.get("scope") or "wg"),
                        ttl=int(data.get("ttl", 300)),
                    )
                else:
                    command = queue_activate(
                        STORE,
                        source_ip=current_source,
                        wan_name=_safe_name(data.get("wan")),
                        wg_name=_safe_name(data.get("wireguard")),
                        ttl=int(data.get("ttl", 300)),
                    )
            except (ValueError, KeyError, GateError) as exc:
                status = 409 if str(exc) == "command_pending" else 400
                self._json(status, {"error": str(exc)})
                return
            self._json(202, {"command_id": command["id"], "state": "pending"})
            return

        if path == "/api/v1/gate/close":
            session = self._require_session()
            if not session or not self._require_csrf(session):
                return
            source = self._trusted_client_ip()
            if not source:
                self._json(400, {"error": "missing_cf_connecting_ip"})
                return
            observe_source(STORE, session.token, source)
            try:
                command = queue_close(STORE, source_ip=source)
            except GateError as exc:
                status = 409 if str(exc) == "command_pending" else 400
                self._json(status, {"error": str(exc)})
                return
            self._json(202, {"command_id": command["id"], "state": "pending"})
            return

        if path == "/api/v1/update":
            if not self._require_agent():
                return
            source = self._trusted_client_ip()
            if not source:
                self._json(400, {"error": "missing_cf_connecting_ip"})
                return
            try:
                data = self._read_json()
                name = _safe_name(data.get("interface"))
                device = _safe_device(data.get("device"))
                ip = _safe_ipv4(data.get("ip"))
            except ValueError:
                self._json(400, {"error": "invalid_update"})
                return
            address_type = "private" if is_private_wan_ipv4(ip) else "public"
            if address_type == "public" and source != ip:
                self._json(403, {"error": "public_source_mismatch"})
                return
            state = STORE.read("current.json", {"schema": 1, "interfaces": {}})
            if not isinstance(state, dict):
                state = {"schema": 1, "interfaces": {}}
            interfaces = state.setdefault("interfaces", {})
            if not isinstance(interfaces, dict):
                interfaces = {}
                state["interfaces"] = interfaces
            now = int(time.time())
            old = interfaces.get(name) if isinstance(interfaces.get(name), dict) else {}
            interfaces[name] = {
                "ip": ip,
                "device": device,
                "address_type": address_type,
                "active": True,
                "changed_at": now if old.get("ip") != ip else int(old.get("changed_at", now)),
                "last_report_at": now,
                "last_report_status": "success",
            }
            STORE.write("current.json", state)
            self._empty(204)
            return

        if path == "/api/v1/inventory":
            if not self._require_agent():
                return
            try:
                data = self._read_json()
                if int(data.get("schema", 1) or 1) == 2:
                    STORE.write("inventory-v2.json", validate_inventory_v2(data))
                    self._empty(204)
                    return

                raw_items = data.get("interfaces", [])
                if not isinstance(raw_items, list) or len(raw_items) > 64:
                    raise ValueError
                incoming = {
                    _safe_name(item.get("name")): _safe_device(item.get("device"))
                    for item in raw_items
                    if isinstance(item, dict)
                }
            except (ValueError, TypeError):
                self._json(400, {"error": "invalid_inventory"})
                return
            state = STORE.read("current.json", {"schema": 1, "interfaces": {}})
            if not isinstance(state, dict):
                state = {"schema": 1, "interfaces": {}}
            interfaces = state.setdefault("interfaces", {})
            if not isinstance(interfaces, dict):
                interfaces = {}
                state["interfaces"] = interfaces
            now = int(time.time())
            for name, record in list(interfaces.items()):
                if not isinstance(record, dict):
                    continue
                if name not in incoming:
                    record["active"] = False
                else:
                    record["active"] = True
                    record["device"] = incoming[name]
            state["last_inventory_at"] = now
            STORE.write("current.json", state)
            self._empty(204)
            return

        if path == "/api/v1/agent/status":
            if not self._require_agent():
                return
            try:
                data = self._read_json()
                schema = max(1, min(2, int(data.get("schema", 1) or 1)))
                wireguard = data.get("wireguard", [])
                if not isinstance(wireguard, list) or len(wireguard) > 32:
                    raise ValueError
                clean_wg = []
                for item in wireguard:
                    if not isinstance(item, dict):
                        continue
                    name = _safe_name(item.get("name"))
                    port = int(item.get("listen_port", 0))
                    if not 1 <= port <= 65535:
                        continue
                    clean_wg.append(
                        {
                            "name": name,
                            "listen_port": port,
                            "latest_handshake": int(item.get("latest_handshake", 0) or 0),
                            "rx": int(item.get("rx", 0) or 0),
                            "tx": int(item.get("tx", 0) or 0),
                        }
                    )
                firewall = data.get("firewall", {})
                if not isinstance(firewall, dict):
                    firewall = {}
                transport = data.get("transport", {})
                if not isinstance(transport, dict):
                    transport = {}
                active_family = str(transport.get("active_family", ""))
                if active_family not in {"ipv4", "ipv6"}:
                    active_family = ""
                active_device = str(transport.get("active_device", ""))[:128]
            except (ValueError, TypeError):
                self._json(400, {"error": "invalid_status"})
                return
            STORE.write(
                "agent-status.json",
                {
                    "schema": schema,
                    "reported_at": int(time.time()),
                    "wireguard": clean_wg,
                    "firewall": {
                        "backend": str(firewall.get("backend", ""))[:32],
                        "ready": bool(firewall.get("ready", False)),
                        "active": bool(firewall.get("active", False)),
                        "family": str(firewall.get("family", ""))[:8],
                        "scope": str(firewall.get("scope", ""))[:16],
                        "expires_in": max(0, int(firewall.get("expires_in", 0) or 0)),
                        "source_ip": str(firewall.get("source_ip", ""))[:64],
                        "device": str(firewall.get("device", ""))[:128],
                        "wg_port": int(firewall.get("wg_port", 0) or 0),
                        "protected_devices_v4": max(0, int(firewall.get("protected_devices_v4", firewall.get("protected_devices", 0)) or 0)),
                        "protected_devices_v6": max(0, int(firewall.get("protected_devices_v6", 0) or 0)),
                        "protected_ports": max(0, int(firewall.get("protected_ports", 0) or 0)),
                    },
                    "transport": {
                        "active_family": active_family,
                        "active_device": active_device,
                        "healthy": bool(transport.get("healthy", False)),
                        "last_ok_at": max(0, int(transport.get("last_ok_at", 0) or 0)),
                    },
                },
            )
            self._empty(204)
            return

        if path == "/api/v1/agent/ack":
            if not self._require_agent():
                return
            data = self._read_json()
            command_id = str(data.get("id", ""))
            ok = bool(data.get("ok", False))
            detail = str(data.get("detail", ""))
            if not command_id or not ack_command(STORE, command_id, ok, detail):
                self._json(409, {"error": "unknown_or_consumed_command"})
                return
            self._empty(204)
            return

        self._empty(404)


def run() -> None:
    server = ThreadingHTTPServer((SETTINGS.bind_host, SETTINGS.bind_port), Handler)
    print(
        f"WeiG-Remote-Gate listening on "
        f"{SETTINGS.bind_host}:{SETTINGS.bind_port} for {SETTINGS.public_hostname}"
    )
    server.serve_forever()


if __name__ == "__main__":
    run()
