from __future__ import annotations

import base64
import ipaddress
import json
import re
import secrets
import threading
import time
from typing import Any

from .control_queue import queue_control_command
from .endpoints import endpoint_by_id
from .gate import GateError
from .store import JsonStore

PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9_. +()\-]{1,48}$")
PROFILE_ID_RE = re.compile(r"^[a-f0-9]{24}$")
COMMAND_ID_RE = re.compile(r"^[a-f0-9]{32}$")
OWNER_KEY_RE = re.compile(r"^[a-f0-9]{64}$")
WG_KEY_RE = re.compile(r"^[A-Za-z0-9+/]{43}=$")
SUPPORTED_FORMATS = {"wireguard", "flclash", "netproxy-8.1.0", "sing-box"}
PROFILE_COMMAND_TTL = 2 * 60 * 60
PROFILE_HISTORY_FILE = "client-profile-history.json"
PROFILE_HISTORY_LIMIT = 100
EXPORT_LOCK = threading.RLock()
EXPORTS: dict[str, dict[str, Any]] = {}
EXPORT_OWNERS: dict[str, dict[str, Any]] = {}
PUBLIC_TOKENS: dict[str, dict[str, Any]] = {}


def _now() -> int:
    return int(time.time())


def _clean_expired(now: int | None = None) -> None:
    current = _now() if now is None else int(now)
    for mapping in (EXPORTS, EXPORT_OWNERS, PUBLIC_TOKENS):
        expired = [key for key, value in mapping.items() if int(value.get("expires_at", 0) or 0) <= current]
        for key in expired:
            mapping.pop(key, None)


def _safe_profile_name(value: object) -> str:
    text = str(value or "").strip()
    if not PROFILE_NAME_RE.fullmatch(text):
        raise GateError("invalid_profile_name")
    return text


def _safe_owner_key(value: object) -> str:
    text = str(value or "").strip()
    if not OWNER_KEY_RE.fullmatch(text):
        raise GateError("invalid_profile_export_owner")
    return text


def _safe_keepalive(value: object) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise GateError("invalid_profile_keepalive") from exc
    if not 0 <= number <= 300:
        raise GateError("invalid_profile_keepalive")
    return number


def _safe_route_mode(value: object) -> str:
    text = str(value or "home").strip()
    if text not in {"home", "full"}:
        raise GateError("invalid_profile_route_mode")
    return text


def _safe_wireguard_key(value: object, error: str) -> str:
    text = str(value or "").strip()
    if not WG_KEY_RE.fullmatch(text):
        raise GateError(error)
    try:
        decoded = base64.b64decode(text, validate=True)
    except Exception as exc:
        raise GateError(error) from exc
    if len(decoded) != 32:
        raise GateError(error)
    return text


def _safe_cidr(value: object, *, version: int | None = None) -> str:
    try:
        interface = ipaddress.ip_interface(str(value or "").strip())
    except ValueError as exc:
        raise GateError("invalid_profile_address") from exc
    if version is not None and interface.version != version:
        raise GateError("invalid_profile_address")
    return str(interface)


def _safe_networks(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > 32:
        raise GateError("invalid_profile_networks")
    result: list[str] = []
    seen: set[str] = set()
    for raw in value:
        try:
            network = ipaddress.ip_network(str(raw or "").strip(), strict=False)
        except ValueError as exc:
            raise GateError("invalid_profile_networks") from exc
        text = str(network)
        if text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _safe_endpoint_address(value: object, family: str) -> str:
    try:
        address = ipaddress.ip_address(str(value or "").strip())
    except ValueError as exc:
        raise GateError("invalid_profile_endpoint") from exc
    expected = 4 if family == "ipv4" else 6
    if address.version != expected:
        raise GateError("invalid_profile_endpoint")
    return str(address)


def _safe_port(value: object) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise GateError("invalid_profile_endpoint") from exc
    if not 1 <= port <= 65535:
        raise GateError("invalid_profile_endpoint")
    return port


def _agent_profile(store: JsonStore, profile_id: str) -> dict[str, Any]:
    status = store.read("agent-status.json", {})
    values = status.get("client_profiles") if isinstance(status, dict) else None
    if not isinstance(values, list):
        raise GateError("profile_not_found")
    for item in values:
        if isinstance(item, dict) and item.get("id") == profile_id:
            return item
    raise GateError("profile_not_found")


def _record_profile_history(store: JsonStore, profile: dict[str, Any]) -> None:
    record = {
        "schema": 1,
        "profile_id": str(profile["id"]),
        "name": str(profile["name"]),
        "wireguard": str(profile["wireguard"]),
        "client_address": str(profile["client_address"]),
        "route_mode": str(profile["route_mode"]),
        "endpoint_family": str(profile["endpoint_family"]),
        "access_method": str(profile["access_method"]),
        "endpoint_address": str(profile["endpoint_address"]),
        "endpoint_port": int(profile["endpoint_port"]),
        "persistent_keepalive": int(profile["persistent_keepalive"]),
        "created_at": int(profile["created_at"]),
        "state": "created",
    }
    history = store.read(PROFILE_HISTORY_FILE, [])
    if not isinstance(history, list):
        history = []
    history = [item for item in history if isinstance(item, dict) and item.get("profile_id") != record["profile_id"]]
    history.append(record)
    store.write(PROFILE_HISTORY_FILE, history[-PROFILE_HISTORY_LIMIT:])


def profile_history(store: JsonStore) -> list[dict[str, Any]]:
    raw = store.read(PROFILE_HISTORY_FILE, [])
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for item in raw[-PROFILE_HISTORY_LIMIT:]:
        if not isinstance(item, dict):
            continue
        try:
            profile_id = str(item.get("profile_id") or "").strip()
            if not PROFILE_ID_RE.fullmatch(profile_id):
                continue
            family = str(item.get("endpoint_family") or "")
            if family not in {"ipv4", "ipv6"}:
                continue
            result.append({
                "schema": 1,
                "profile_id": profile_id,
                "name": _safe_profile_name(item.get("name")),
                "wireguard": str(item.get("wireguard") or "")[:64],
                "client_address": _safe_cidr(item.get("client_address"), version=4),
                "route_mode": _safe_route_mode(item.get("route_mode")),
                "endpoint_family": family,
                "access_method": str(item.get("access_method") or "")[:16],
                "endpoint_address": _safe_endpoint_address(item.get("endpoint_address"), family),
                "endpoint_port": _safe_port(item.get("endpoint_port")),
                "persistent_keepalive": _safe_keepalive(item.get("persistent_keepalive")),
                "created_at": max(0, int(item.get("created_at", 0) or 0)),
                "state": "created",
            })
        except (GateError, TypeError, ValueError):
            continue
    result.sort(key=lambda item: int(item.get("created_at", 0)), reverse=True)
    return result


def queue_profile_create(
    store: JsonStore,
    *,
    name: object,
    endpoint_id: object,
    route_mode: object = "home",
    persistent_keepalive: object = 25,
    owner_key: object | None = None,
) -> dict[str, Any]:
    profile_name = _safe_profile_name(name)
    endpoint_key = str(endpoint_id or "").strip()
    endpoint = endpoint_by_id(store, endpoint_key)
    family = str(endpoint.get("family") or "")
    access_method = str(endpoint.get("access_method") or "direct")
    if family not in {"ipv4", "ipv6"} or access_method not in {"direct", "mapped"}:
        raise GateError("profile_endpoint_unavailable")
    if endpoint.get("reachability") not in {"direct", "mapped"}:
        raise GateError("profile_endpoint_unavailable")
    service_type = str(endpoint.get("service_type") or "wireguard")
    wireguard = str(endpoint.get("wireguard") or "")
    service_id = str(endpoint.get("service_id") or "")
    if service_type != "wireguard" or not wireguard or service_id != f"wg.{wireguard}":
        raise GateError("profile_wireguard_unavailable")
    service_port = _safe_port(endpoint.get("service_port", endpoint.get("local_port", 0)))
    external_port = _safe_port(endpoint.get("external_port", endpoint.get("ingress_port", service_port)))
    external_address = _safe_endpoint_address(endpoint.get("external_address"), family)
    mode = _safe_route_mode(route_mode)
    keepalive = _safe_keepalive(persistent_keepalive)
    owner = _safe_owner_key(owner_key) if owner_key not in (None, "") else ""
    now = _now()
    command = {
        "schema": 1,
        "id": secrets.token_hex(16),
        "action": "profile_create",
        "created_at": now,
        "expires_at": now + PROFILE_COMMAND_TTL,
        "profile_id": secrets.token_hex(12),
        "profile_name": profile_name,
        "route_mode": mode,
        "persistent_keepalive": keepalive,
        "endpoint_id": endpoint_key,
        "family": family,
        "access_method": access_method,
        "wan": str(endpoint.get("wan") or ""),
        "device": str(endpoint.get("device") or ""),
        "service_id": service_id,
        "service_type": "wireguard",
        "wireguard": wireguard,
        "service_port": service_port,
        "external_address": external_address,
        "external_port": external_port,
        "state": "pending",
    }
    if owner:
        with EXPORT_LOCK:
            _clean_expired(now)
            EXPORT_OWNERS[command["id"]] = {"owner_key": owner, "expires_at": command["expires_at"]}
    try:
        queue_control_command(store, command)
    except Exception:
        if owner:
            with EXPORT_LOCK:
                EXPORT_OWNERS.pop(command["id"], None)
        raise
    return command


def queue_profile_revoke(store: JsonStore, profile_id: object) -> dict[str, Any]:
    key = str(profile_id or "").strip()
    if not PROFILE_ID_RE.fullmatch(key):
        raise GateError("invalid_profile_id")
    profile = _agent_profile(store, key)
    now = _now()
    command = {
        "schema": 1,
        "id": secrets.token_hex(16),
        "action": "profile_revoke",
        "created_at": now,
        "expires_at": now + PROFILE_COMMAND_TTL,
        "profile_id": key,
        "wireguard": str(profile.get("wireguard") or ""),
        "public_key": str(profile.get("public_key") or ""),
        "state": "pending",
    }
    queue_control_command(store, command)
    return command


def _expected_profile_command(store: JsonStore, command_id: str) -> dict[str, Any]:
    queue = store.read("commands.json", {})
    if not isinstance(queue, dict):
        raise GateError("profile_command_not_found")
    for key in ("pending", "last"):
        item = queue.get(key)
        if isinstance(item, dict) and item.get("id") == command_id and item.get("action") == "profile_create":
            return item
    raise GateError("profile_command_not_found")


def profile_command_owned(command_id: object, owner_key: object) -> bool:
    key = str(command_id or "").strip()
    if not COMMAND_ID_RE.fullmatch(key):
        return False
    try:
        owner = _safe_owner_key(owner_key)
    except GateError:
        return False
    with EXPORT_LOCK:
        _clean_expired()
        record = EXPORT_OWNERS.get(key)
        return isinstance(record, dict) and record.get("owner_key") == owner


def accept_profile_result(store: JsonStore, payload: object, *, ttl_seconds: int) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise GateError("invalid_profile_result")
    command_id = str(payload.get("command_id") or "").strip()
    if not COMMAND_ID_RE.fullmatch(command_id):
        raise GateError("invalid_profile_result")
    command = _expected_profile_command(store, command_id)
    raw = payload.get("profile")
    if not isinstance(raw, dict):
        raise GateError("invalid_profile_result")

    profile_id = str(raw.get("id") or "").strip()
    if profile_id != command.get("profile_id") or not PROFILE_ID_RE.fullmatch(profile_id):
        raise GateError("profile_result_mismatch")
    name = _safe_profile_name(raw.get("name"))
    if name != command.get("profile_name"):
        raise GateError("profile_result_mismatch")
    wireguard = str(raw.get("wireguard") or "").strip()
    if wireguard != command.get("wireguard"):
        raise GateError("profile_result_mismatch")
    route_mode = _safe_route_mode(raw.get("route_mode"))
    if route_mode != command.get("route_mode"):
        raise GateError("profile_result_mismatch")
    keepalive = _safe_keepalive(raw.get("persistent_keepalive"))
    if keepalive != int(command.get("persistent_keepalive", -1)):
        raise GateError("profile_result_mismatch")

    family = str(command.get("family") or "")
    endpoint_address = _safe_endpoint_address(raw.get("endpoint_address"), family)
    endpoint_port = _safe_port(raw.get("endpoint_port"))
    if endpoint_address != command.get("external_address") or endpoint_port != int(command.get("external_port", 0) or 0):
        if command.get("access_method") != "mapped":
            raise GateError("profile_result_mismatch")

    mtu_raw = raw.get("mtu")
    mtu: int | None = None
    if mtu_raw not in (None, "", 0):
        try:
            mtu = int(mtu_raw)
        except (TypeError, ValueError) as exc:
            raise GateError("invalid_profile_mtu") from exc
        if not 576 <= mtu <= 9000:
            raise GateError("invalid_profile_mtu")

    dns = str(raw.get("dns") or "").strip()
    if len(dns) > 128 or any(ch in dns for ch in "\r\n"):
        raise GateError("invalid_profile_dns")
    profile = {
        "schema": 1,
        "id": profile_id,
        "name": name,
        "wireguard": wireguard,
        "client_address": _safe_cidr(raw.get("client_address"), version=4),
        "private_key": _safe_wireguard_key(raw.get("private_key"), "invalid_profile_private_key"),
        "public_key": _safe_wireguard_key(raw.get("public_key"), "invalid_profile_public_key"),
        "server_public_key": _safe_wireguard_key(raw.get("server_public_key"), "invalid_profile_server_key"),
        "endpoint_family": family,
        "endpoint_address": endpoint_address,
        "endpoint_port": endpoint_port,
        "access_method": str(command.get("access_method") or "direct"),
        "route_mode": route_mode,
        "home_networks": _safe_networks(raw.get("home_networks", [])),
        "dns": dns,
        "mtu": mtu,
        "persistent_keepalive": keepalive,
        "created_at": max(0, int(raw.get("created_at", _now()) or 0)),
    }
    _record_profile_history(store, profile)
    now = _now()
    expires_at = now + ttl_seconds
    owner = ""
    with EXPORT_LOCK:
        _clean_expired(now)
        owner_record = EXPORT_OWNERS.get(command_id)
        if isinstance(owner_record, dict):
            owner = str(owner_record.get("owner_key") or "")
        EXPORTS[command_id] = {"profile": profile, "expires_at": expires_at, "owner_key": owner}
        if owner:
            EXPORT_OWNERS[command_id] = {"owner_key": owner, "expires_at": expires_at}
    return public_profile(profile, export_available=bool(owner), export_expires_at=expires_at if owner else 0)


def sanitize_agent_profiles(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 64:
        return []
    result: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        try:
            profile_id = str(raw.get("id") or "").strip()
            if not PROFILE_ID_RE.fullmatch(profile_id):
                continue
            item = {
                "schema": 1,
                "id": profile_id,
                "name": _safe_profile_name(raw.get("name")),
                "wireguard": str(raw.get("wireguard") or "")[:64],
                "public_key": _safe_wireguard_key(raw.get("public_key"), "invalid"),
                "client_address": _safe_cidr(raw.get("client_address"), version=4),
                "route_mode": _safe_route_mode(raw.get("route_mode")),
                "endpoint_family": str(raw.get("endpoint_family") or "")[:8],
                "access_method": str(raw.get("access_method") or "")[:16],
                "endpoint_address": str(raw.get("endpoint_address") or "")[:128],
                "endpoint_port": _safe_port(raw.get("endpoint_port")),
                "persistent_keepalive": _safe_keepalive(raw.get("persistent_keepalive")),
                "home_networks": _safe_networks(raw.get("home_networks", [])),
                "created_at": max(0, int(raw.get("created_at", 0) or 0)),
            }
        except (GateError, TypeError, ValueError):
            continue
        result.append(item)
    return result


def public_profile(profile: dict[str, Any], *, export_available: bool = False, export_expires_at: int = 0) -> dict[str, Any]:
    result = {key: value for key, value in profile.items() if key != "private_key"}
    result["export_available"] = bool(export_available)
    result["export_expires_at"] = int(export_expires_at or 0)
    result["formats"] = sorted(SUPPORTED_FORMATS)
    result["mapped_snapshot"] = result.get("access_method") == "mapped"
    return result


def result_view(command_id: object, owner_key: object | None = None) -> dict[str, Any] | None:
    key = str(command_id or "").strip()
    if not COMMAND_ID_RE.fullmatch(key):
        raise GateError("invalid_profile_command")
    owner = _safe_owner_key(owner_key) if owner_key not in (None, "") else None
    with EXPORT_LOCK:
        _clean_expired()
        item = EXPORTS.get(key)
        if not isinstance(item, dict):
            return None
        if owner is not None and item.get("owner_key") != owner:
            raise GateError("profile_export_expired")
        profile = item.get("profile")
        if not isinstance(profile, dict):
            return None
        return public_profile(profile, export_available=bool(item.get("owner_key")), export_expires_at=int(item.get("expires_at", 0) or 0))


def recent_results(owner_key: object) -> list[dict[str, Any]]:
    owner = _safe_owner_key(owner_key)
    with EXPORT_LOCK:
        _clean_expired()
        result: list[dict[str, Any]] = []
        for command_id, item in EXPORTS.items():
            if not isinstance(item, dict) or item.get("owner_key") != owner:
                continue
            profile = item.get("profile")
            if not isinstance(profile, dict):
                continue
            result.append({
                "command_id": command_id,
                "profile": public_profile(profile, export_available=True, export_expires_at=int(item.get("expires_at", 0) or 0)),
            })
        result.sort(key=lambda item: int(item.get("profile", {}).get("created_at", 0)), reverse=True)
        return result


def _profile_for_export(command_id: str, owner_key: object | None = None) -> dict[str, Any]:
    owner = _safe_owner_key(owner_key) if owner_key not in (None, "") else None
    with EXPORT_LOCK:
        _clean_expired()
        item = EXPORTS.get(command_id)
        if not isinstance(item, dict) or not isinstance(item.get("profile"), dict):
            raise GateError("profile_export_expired")
        if owner is not None and item.get("owner_key") != owner:
            raise GateError("profile_export_expired")
        return dict(item["profile"])


def _yaml_string(value: object) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _endpoint_for_wireguard(profile: dict[str, Any]) -> str:
    address = str(profile["endpoint_address"])
    if ":" in address:
        address = f"[{address}]"
    return f"{address}:{int(profile['endpoint_port'])}"


def _wireguard_allowed(profile: dict[str, Any]) -> list[str]:
    if profile.get("route_mode") == "full":
        return ["0.0.0.0/0"]
    networks = [str(x) for x in profile.get("home_networks", []) if str(x)]
    return networks or [str(ipaddress.ip_interface(profile["client_address"]).network)]


def render_wireguard(profile: dict[str, Any]) -> str:
    lines = ["[Interface]", f"PrivateKey = {profile['private_key']}", f"Address = {profile['client_address']}"]
    if profile.get("dns"):
        lines.append(f"DNS = {profile['dns']}")
    if profile.get("mtu"):
        lines.append(f"MTU = {profile['mtu']}")
    lines.extend(["", "[Peer]", f"PublicKey = {profile['server_public_key']}", f"Endpoint = {_endpoint_for_wireguard(profile)}", f"AllowedIPs = {', '.join(_wireguard_allowed(profile))}", f"PersistentKeepalive = {int(profile['persistent_keepalive'])}", ""])
    return "\n".join(lines)


def _mihomo_proxy_lines(profile: dict[str, Any], *, indent: str = "  ") -> list[str]:
    client_ip = str(ipaddress.ip_interface(profile["client_address"]).ip)
    name = f"RemoteGate - {profile['name']}"
    lines = [
        f"{indent}- name: {_yaml_string(name)}", f"{indent}  type: wireguard", f"{indent}  server: {_yaml_string(profile['endpoint_address'])}",
        f"{indent}  port: {int(profile['endpoint_port'])}", f"{indent}  ip: {_yaml_string(client_ip)}", f"{indent}  private-key: {_yaml_string(profile['private_key'])}",
        f"{indent}  public-key: {_yaml_string(profile['server_public_key'])}", f"{indent}  udp: true", f"{indent}  allowed-ips:", f"{indent}    - 0.0.0.0/0",
        f"{indent}  persistent-keepalive: {int(profile['persistent_keepalive'])}",
    ]
    if profile.get("mtu"):
        lines.append(f"{indent}  mtu: {int(profile['mtu'])}")
    return lines


def render_flclash(profile: dict[str, Any]) -> str:
    node = f"RemoteGate - {profile['name']}"
    lines = ["# WeiG Remote Gate / FlClash (Mihomo) profile", "mixed-port: 7890", "allow-lan: false", "mode: rule", "log-level: info", "proxies:", *_mihomo_proxy_lines(profile), "proxy-groups:", "  - name: RemoteGate", "    type: select", "    proxies:", f"      - {_yaml_string(node)}", "      - DIRECT", "rules:"]
    if profile.get("route_mode") == "full":
        lines.append("  - MATCH,RemoteGate")
    else:
        for network in _wireguard_allowed(profile):
            rule_type = "IP-CIDR6" if ":" in network else "IP-CIDR"
            lines.append(f"  - {rule_type},{network},RemoteGate,no-resolve")
        lines.append("  - MATCH,DIRECT")
    lines.append("")
    return "\n".join(lines)


def render_netproxy_810(profile: dict[str, Any]) -> str:
    lines = ["# WeiG Remote Gate / NetProxy 8.1.0 node import", "# Import with: netproxyctl node import /sdcard/remote-gate.yaml", f"# Requested route mode: {profile['route_mode']} (select routing mode inside NetProxy)", "proxies:", *_mihomo_proxy_lines(profile), ""]
    return "\n".join(lines)


def render_sing_box(profile: dict[str, Any]) -> str:
    endpoint: dict[str, Any] = {
        "type": "wireguard", "tag": f"RemoteGate-{profile['id'][:8]}", "address": [profile["client_address"]], "private_key": profile["private_key"],
        "peers": [{"address": profile["endpoint_address"], "port": int(profile["endpoint_port"]), "public_key": profile["server_public_key"], "allowed_ips": _wireguard_allowed(profile), "persistent_keepalive_interval": int(profile["persistent_keepalive"])}],
    }
    if profile.get("mtu"):
        endpoint["mtu"] = int(profile["mtu"])
    return json.dumps({"endpoints": [endpoint]}, ensure_ascii=False, indent=2) + "\n"


def render_format(command_id: object, fmt: object, owner_key: object | None = None) -> tuple[str, str, bytes]:
    key = str(command_id or "").strip(); format_name = str(fmt or "").strip()
    if not COMMAND_ID_RE.fullmatch(key) or format_name not in SUPPORTED_FORMATS:
        raise GateError("invalid_profile_export")
    profile = _profile_for_export(key, owner_key)
    if format_name == "wireguard": text, content_type, ext = render_wireguard(profile), "text/plain; charset=utf-8", "conf"
    elif format_name == "flclash": text, content_type, ext = render_flclash(profile), "application/yaml; charset=utf-8", "yaml"
    elif format_name == "netproxy-8.1.0": text, content_type, ext = render_netproxy_810(profile), "application/yaml; charset=utf-8", "yaml"
    else: text, content_type, ext = render_sing_box(profile), "application/json; charset=utf-8", "json"
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(profile["name"]).strip()).strip("-") or "remote-gate"
    return content_type, f"{safe_name}.{format_name}.{ext}", text.encode("utf-8")


def create_public_token(command_id: object, fmt: object, *, ttl_seconds: int, public_base: str, owner_key: object | None = None) -> dict[str, Any]:
    key = str(command_id or "").strip(); format_name = str(fmt or "").strip()
    if format_name not in {"flclash", "netproxy-8.1.0", "sing-box"}:
        raise GateError("profile_qr_not_supported")
    _profile_for_export(key, owner_key)
    owner = _safe_owner_key(owner_key) if owner_key not in (None, "") else ""
    now = _now(); token = secrets.token_urlsafe(24)
    with EXPORT_LOCK:
        _clean_expired(now); PUBLIC_TOKENS[token] = {"command_id": key, "format": format_name, "owner_key": owner, "expires_at": now + ttl_seconds}
    return {"token": token, "url": f"{public_base.rstrip('/')}/p/{token}", "expires_at": now + ttl_seconds}


def consume_public_token(token: object) -> tuple[str, str, bytes]:
    key = str(token or "").strip()
    if len(key) < 20 or len(key) > 128:
        raise GateError("profile_share_expired")
    with EXPORT_LOCK:
        _clean_expired(); item = PUBLIC_TOKENS.pop(key, None)
    if not isinstance(item, dict):
        raise GateError("profile_share_expired")
    return render_format(item["command_id"], item["format"], item.get("owner_key") or None)
