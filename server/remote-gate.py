#!/usr/bin/env python3
from __future__ import annotations

import ipaddress
import re
import time
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse

from app.client_sources import observe_candidate, observe_source, source_record_for_family
from app.endpoints import is_globally_reachable_unicast, validate_inventory_v2, validate_inventory_v3
from app.gate import GateError, queue_activate, queue_activate_many
from app.main import Handler as BaseHandler
from app.main import SETTINGS, STORE

ENDPOINT_RE = re.compile(r"^ep_[a-f0-9]{20}$")
NAME_RE = re.compile(r"^[A-Za-z0-9_.:@-]{1,64}$")
DEVICE_RE = re.compile(r"^[A-Za-z0-9_.:@+-]{1,128}$")
EGRESS_MODES = {"none", "ipv4", "ipv6", "dual"}


def _endpoint_id(value: object) -> str:
    text = str(value or "").strip()
    if not ENDPOINT_RE.fullmatch(text):
        raise ValueError("invalid_endpoint")
    return text


def _family(value: object) -> str:
    text = str(value or "").strip()
    if text not in {"ipv4", "ipv6"}:
        raise ValueError("invalid_family")
    return text


def _egress_mode(value: object) -> str:
    text = str(value or "").strip()
    if text not in EGRESS_MODES:
        raise ValueError("invalid_egress_mode")
    return text


def _candidate(value: object, family: str) -> str:
    address = ipaddress.ip_address(str(value or "").strip())
    version = 4 if family == "ipv4" else 6
    if address.version != version or not is_globally_reachable_unicast(address, version=version):
        raise ValueError("invalid_candidate")
    return str(address)


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


def _clean_authorization(value: object, family: str) -> dict | None:
    if not isinstance(value, dict):
        return None
    try:
        address = ipaddress.ip_address(str(value.get("source_ip") or "").strip())
        expected = 4 if family == "ipv4" else 6
        expires = max(0, int(value.get("expires_in", 0) or 0))
    except (ValueError, TypeError):
        return None
    if address.version != expected:
        return None
    return {
        "source_ip": str(address),
        "source_kind": str(value.get("source_kind", ""))[:32],
        "expires_in": expires,
    }


def _clean_fw_family(value: object, family: str) -> dict:
    item = value if isinstance(value, dict) else {}
    try:
        port = max(0, int(item.get("wg_port", item.get("ingress_port", 0)) or 0))
        ingress_port = max(0, int(item.get("ingress_port", port) or 0))
        expires = max(0, int(item.get("expires_in", 0) or 0))
    except (TypeError, ValueError):
        port = 0
        ingress_port = 0
        expires = 0
    result = {
        "active": bool(item.get("active", False)),
        "family": family,
        "scope": str(item.get("scope", ""))[:16],
        "expires_in": expires,
        "source_ip": str(item.get("source_ip", ""))[:64],
        "source_kind": str(item.get("source_kind", ""))[:32],
        "device": str(item.get("device", ""))[:128],
        "wg_port": port,
        "ingress_port": ingress_port,
    }

    sources_known = isinstance(item.get("authorized_sources"), list)
    entries_known = isinstance(item.get("authorizations"), list)
    entries: list[dict] = []
    if entries_known:
        for raw in item.get("authorizations", [])[:64]:
            clean = _clean_authorization(raw, family)
            if clean is not None:
                entries.append(clean)

    if sources_known or entries_known:
        sources: list[str] = []
        seen: set[str] = set()
        raw_sources = item.get("authorized_sources", []) if sources_known else []
        for raw in raw_sources[:64]:
            try:
                address = ipaddress.ip_address(str(raw or "").strip())
            except ValueError:
                continue
            expected = 4 if family == "ipv4" else 6
            if address.version != expected:
                continue
            text = str(address)
            if text not in seen:
                seen.add(text)
                sources.append(text)
        for entry in entries:
            text = entry["source_ip"]
            if text not in seen:
                seen.add(text)
                sources.append(text)
        result["authorized_sources"] = sources
        result["authorizations"] = entries
        result["source_count"] = len(sources)
        result["active"] = bool(result["active"] and sources)
    return result


def _clean_network(value: object, version: int) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        network = ipaddress.ip_network(text, strict=False)
    except ValueError:
        return ""
    return str(network) if network.version == version else ""


def _clean_egress(value: object) -> dict:
    item = value if isinstance(value, dict) else {}
    state = str(item.get("state") or "inactive").strip()
    if state not in {"inactive", "active", "failed"}:
        state = "inactive"
    mode = str(item.get("mode") or "").strip()
    if mode not in {"", "ipv4", "ipv6", "dual"}:
        mode = ""

    def clean_name(key: str) -> str:
        text = str(item.get(key) or "").strip()
        return text if not text or NAME_RE.fullmatch(text) else ""

    def clean_device(key: str) -> str:
        text = str(item.get(key) or "").strip()
        return text if not text or DEVICE_RE.fullmatch(text) else ""

    wan = clean_name("wan")
    device = clean_device("device")
    wan_v4 = clean_name("wan_v4")
    device_v4 = clean_device("device_v4")
    wan_v6 = clean_name("wan_v6")
    device_v6 = clean_device("device_v6")
    if mode in {"ipv4", "dual"} and not wan_v4:
        wan_v4, device_v4 = wan, device
    if mode in {"ipv6", "dual"} and not wan_v6:
        wan_v6, device_v6 = wan, device

    wg = str(item.get("wg") or "").strip()
    if wg and not NAME_RE.fullmatch(wg):
        wg = ""
    try:
        expires = max(0, int(item.get("expires_in", 0) or 0))
    except (TypeError, ValueError):
        expires = 0
    detail = re.sub(r"[^A-Za-z0-9 ._:/(),+\-]", "_", str(item.get("detail") or ""))[:200]
    active = bool(item.get("active", False)) and state == "active"
    if state == "active" and not active:
        state = "inactive"
    return {
        "active": active,
        "state": state,
        "mode": mode,
        "wan": wan,
        "device": device,
        "wan_v4": wan_v4,
        "device_v4": device_v4,
        "wan_v6": wan_v6,
        "device_v6": device_v6,
        "wg": wg,
        "ipv4_subnet": _clean_network(item.get("ipv4_subnet"), 4),
        "ipv6_subnet": _clean_network(item.get("ipv6_subnet"), 6),
        "detail": detail,
        "expires_in": expires,
    }


def _clean_mapping_status(value: object) -> dict:
    item = value if isinstance(value, dict) else {}
    state = str(item.get("state") or "unavailable").strip().lower()
    if state not in {"unavailable", "idle", "preparing", "active", "failed"}:
        state = "unavailable"
    try:
        active = max(0, min(64, int(item.get("active_mappings", 0) or 0)))
    except (TypeError, ValueError):
        active = 0
    detail = re.sub(r"[^A-Za-z0-9 ._:/(),+\-]", "_", str(item.get("detail") or ""))[:200]
    return {
        "available": bool(item.get("available", False)),
        "state": state,
        "active_mappings": active,
        "detail": detail,
    }


def _sanitize_inventory(data: dict) -> dict:
    schema = int(data.get("schema", 0) or 0)
    if schema == 3:
        return validate_inventory_v3(data)
    if schema == 2:
        return validate_inventory_v2(data)
    raise ValueError("unsupported_inventory_schema")


def _sanitize_stored_inventory() -> None:
    raw3 = STORE.read("inventory-v3.json", {})
    if isinstance(raw3, dict) and int(raw3.get("schema", 0) or 0) == 3:
        try:
            clean3 = validate_inventory_v3(raw3)
        except (ValueError, TypeError):
            clean3 = None
        if clean3 is not None and clean3 != raw3:
            STORE.write("inventory-v3.json", clean3)

    raw2 = STORE.read("inventory-v2.json", {})
    if isinstance(raw2, dict) and int(raw2.get("schema", 0) or 0) == 2:
        try:
            clean2 = validate_inventory_v2(raw2)
        except (ValueError, TypeError):
            clean2 = None
        if clean2 is not None and clean2 != raw2:
            STORE.write("inventory-v2.json", clean2)


class Handler(BaseHandler):
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
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self' https://api.ipify.org https://api6.ipify.org https://api-ipv4.ip.sb https://api-ipv6.ip.sb; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/api/v1/dashboard":
            _sanitize_stored_inventory()
        super().do_GET()

    def _candidate_post(self) -> None:
        if not self._host_ok():
            return
        session = self._require_session()
        if not session or not self._require_csrf(session):
            return
        try:
            data = self._read_json()
            family = _family(data.get("family"))
            address = _candidate(data.get("address"), family)
            record = observe_candidate(STORE, session.token, address, family)
        except (ValueError, TypeError):
            self._json(400, {"error": "invalid_source_candidate"})
            return
        if record.get("confidence") == "suppressed":
            self._json(409, {"error": "router_egress_source"})
            return
        self._json(200, record)

    def _activate_post(self) -> None:
        if not self._host_ok():
            return
        session = self._require_session()
        if not session or not self._require_csrf(session):
            return
        current_source = self._trusted_client_ip()
        if not current_source:
            self._json(400, {"error": "missing_cf_connecting_ip"})
            return
        try:
            observe_source(STORE, session.token, current_source)
            data = self._read_json()
            ttl = int(data.get("ttl", 300))
            scope = str(data.get("scope") or "wg")
            egress_mode_raw = str(data.get("egress_mode") or "").strip()
            egress_mode = _egress_mode(egress_mode_raw) if egress_mode_raw else ""
            egress_raw = str(data.get("egress_wan") or "").strip()
            egress_name = _safe_name(egress_raw) if egress_raw else ""
            egress_names = None
            egress_map = data.get("egress_wans")
            if egress_map is not None:
                if not isinstance(egress_map, dict) or any(key not in {"ipv4", "ipv6"} for key in egress_map):
                    raise ValueError("invalid_egress_wans")
                egress_names = {}
                for egress_family in ("ipv4", "ipv6"):
                    raw = str(egress_map.get(egress_family) or "").strip()
                    if raw:
                        egress_names[egress_family] = _safe_name(raw)
            families_raw = data.get("families")
            if isinstance(families_raw, list):
                families = [_family(value) for value in families_raw]
                if not 1 <= len(families) <= 2 or len(set(families)) != len(families):
                    raise GateError("invalid_families")
                endpoint_ids = data.get("endpoint_ids")
                if not isinstance(endpoint_ids, dict):
                    raise GateError("endpoint_required")
                requests = []
                for family in families:
                    source = source_record_for_family(STORE, session.token, family)
                    requests.append({
                        "family": family,
                        "source_ip": source["address"],
                        "source_confidence": source.get("confidence", "verified"),
                        "endpoint_id": _endpoint_id(endpoint_ids.get(family)),
                    })
                batch = queue_activate_many(
                    STORE,
                    requests,
                    scope=scope,
                    ttl=ttl,
                    egress_name=egress_name,
                    egress_names=egress_names,
                    egress_mode=egress_mode or None,
                )
                self._json(202, {
                    "batch_id": batch["batch_id"],
                    "command_id": batch["pending"]["id"],
                    "count": len(batch["commands"]),
                    "state": "pending",
                })
                return
            family = _family(data.get("family"))
            source = source_record_for_family(STORE, session.token, family)
            command = queue_activate(
                STORE,
                source_ip=str(source["address"]),
                source_confidence=str(source.get("confidence") or "verified"),
                endpoint_id=_endpoint_id(data.get("endpoint_id")),
                family=family,
                scope=scope,
                ttl=ttl,
                egress_name=egress_name,
                egress_names=egress_names,
                egress_mode=egress_mode or None,
            )
        except (ValueError, KeyError, GateError) as exc:
            self._json(409 if str(exc) == "command_pending" else 400, {"error": str(exc)})
            return
        self._json(202, {"command_id": command["id"], "state": "pending"})

    def _inventory_post(self) -> None:
        if not self._host_ok() or not self._require_agent():
            return
        try:
            data = self._read_json()
            schema = int(data.get("schema", 1) or 1)
            if schema == 3:
                STORE.write("inventory-v3.json", validate_inventory_v3(data))
                self._empty(204)
                return
            if schema == 2:
                STORE.write("inventory-v3.json", {})
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
        STORE.write("inventory-v3.json", {})
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
            record["active"] = name in incoming
            if name in incoming:
                record["device"] = incoming[name]
        state["last_inventory_at"] = now
        STORE.write("current.json", state)
        self._empty(204)

    def _agent_status_post(self) -> None:
        if not self._host_ok() or not self._require_agent():
            return
        try:
            data = self._read_json()
            schema = max(1, min(3, int(data.get("schema", 1) or 1)))
            wireguard = data.get("wireguard", [])
            if not isinstance(wireguard, list) or len(wireguard) > 32:
                raise ValueError
            clean_wg = []
            for item in wireguard:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "")[:64]
                port = int(item.get("listen_port", 0) or 0)
                if not name or not 1 <= port <= 65535:
                    continue
                clean_wg.append({
                    "name": name,
                    "listen_port": port,
                    "latest_handshake": int(item.get("latest_handshake", 0) or 0),
                    "rx": int(item.get("rx", 0) or 0),
                    "tx": int(item.get("tx", 0) or 0),
                })
            firewall = data.get("firewall", {}) if isinstance(data.get("firewall"), dict) else {}
            raw = firewall.get("families") if isinstance(firewall.get("families"), dict) else {}
            families = {
                "ipv4": _clean_fw_family(raw.get("ipv4"), "ipv4"),
                "ipv6": _clean_fw_family(raw.get("ipv6"), "ipv6"),
            }
            if not any(x["active"] for x in families.values()) and bool(firewall.get("active", False)):
                old_family = str(firewall.get("family", ""))
                if old_family in families:
                    families[old_family] = _clean_fw_family(firewall, old_family)
            egress = _clean_egress(data.get("egress"))
            transport = data.get("transport", {}) if isinstance(data.get("transport"), dict) else {}
            mapping = _clean_mapping_status(data.get("mapping"))
        except (ValueError, TypeError):
            self._json(400, {"error": "invalid_status"})
            return
        active = [x for x in families.values() if x["active"]]
        primary = active[0] if active else {}
        STORE.write("agent-status.json", {
            "schema": schema,
            "reported_at": int(time.time()),
            "wireguard": clean_wg,
            "firewall": {
                "backend": str(firewall.get("backend", ""))[:32],
                "ready": bool(firewall.get("ready", False)),
                "ipv6_capable": bool(firewall.get("ipv6_capable", False)),
                "active": bool(active),
                "family": str(primary.get("family", "")),
                "scope": str(primary.get("scope", "")),
                "expires_in": int(primary.get("expires_in", 0) or 0),
                "source_ip": str(primary.get("source_ip", "")),
                "device": str(primary.get("device", "")),
                "wg_port": int(primary.get("wg_port", 0) or 0),
                "ingress_port": int(primary.get("ingress_port", primary.get("wg_port", 0)) or 0),
                "families": families,
                "protected_devices_v4": max(0, int(firewall.get("protected_devices_v4", firewall.get("protected_devices", 0)) or 0)),
                "protected_devices_v6": max(0, int(firewall.get("protected_devices_v6", 0) or 0)),
                "protected_ports": max(0, int(firewall.get("protected_ports", 0) or 0)),
            },
            "egress": egress,
            "mapping": mapping,
            "transport": {
                "active_family": str(transport.get("active_family", ""))[:8],
                "active_device": str(transport.get("active_device", ""))[:128],
                "healthy": bool(transport.get("healthy", False)),
                "last_ok_at": max(0, int(transport.get("last_ok_at", 0) or 0)),
            },
        })
        self._empty(204)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/v1/client-source/probe":
            if not self._host_ok():
                return
            self._json(410, {"error": "legacy_source_probe_disabled"})
            return
        if path == "/api/v1/client-source/candidate":
            self._candidate_post()
            return
        if path == "/api/v1/gate/activate":
            self._activate_post()
            return
        if path == "/api/v1/inventory":
            self._inventory_post()
            return
        if path == "/api/v1/agent/status":
            self._agent_status_post()
            return
        super().do_POST()


def run() -> None:
    server = ThreadingHTTPServer((SETTINGS.bind_host, SETTINGS.bind_port), Handler)
    print(f"WeiG-Remote-Gate listening on {SETTINGS.bind_host}:{SETTINGS.bind_port} for {SETTINGS.public_hostname}")
    server.serve_forever()


if __name__ == "__main__":
    run()
