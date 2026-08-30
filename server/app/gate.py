from __future__ import annotations

import ipaddress
import secrets
import threading
import time
from typing import Any

from .endpoints import endpoint_by_id, normalize_inventory
from .store import JsonStore


ALLOWED_TTLS = {60, 300, 900, 1800}
ALLOWED_SCOPES = {"wg", "wg_ping"}
QUEUE_LOCK = threading.RLock()


class GateError(ValueError):
    pass


def normalize_current(store: JsonStore) -> dict[str, Any]:
    state = store.read("current.json", {"schema": 1, "interfaces": {}})
    if not isinstance(state, dict):
        state = {"schema": 1, "interfaces": {}}
    interfaces = state.get("interfaces")
    if not isinstance(interfaces, dict):
        state["interfaces"] = {}
    return state


def public_wan(store: JsonStore, name: str) -> dict[str, Any]:
    """Schema-1 compatibility path used during rolling upgrades."""
    state = normalize_current(store)
    record = state["interfaces"].get(name)
    if not isinstance(record, dict) or not record.get("active"):
        raise GateError("wan_unavailable")
    if record.get("address_type") != "public":
        raise GateError("wan_not_public")
    if not record.get("ip") or not record.get("device"):
        raise GateError("wan_incomplete")
    return record


def wireguard_interface(store: JsonStore, name: str) -> dict[str, Any]:
    status = store.read("agent-status.json", {})
    interfaces = status.get("wireguard") if isinstance(status, dict) else None
    if not isinstance(interfaces, list):
        raise GateError("wireguard_unavailable")
    for item in interfaces:
        if isinstance(item, dict) and item.get("name") == name:
            try:
                port = int(item.get("listen_port", 0) or 0)
            except (TypeError, ValueError):
                continue
            if 1 <= port <= 65535:
                return item
    raise GateError("wireguard_unavailable")


def _agent_schema(store: JsonStore) -> int:
    status = store.read("agent-status.json", {})
    if not isinstance(status, dict):
        return 1
    try:
        return max(1, int(status.get("schema", 1) or 1))
    except (TypeError, ValueError):
        return 1


def _source_address(source_ip: str, family: str | None = None):
    try:
        address = ipaddress.ip_address(source_ip)
    except ValueError as exc:
        raise GateError("invalid_source_ip") from exc
    expected = family or ("ipv4" if address.version == 4 else "ipv6")
    if expected not in {"ipv4", "ipv6"}:
        raise GateError("invalid_family")
    if (expected == "ipv4" and address.version != 4) or (expected == "ipv6" and address.version != 6):
        raise GateError("source_family_mismatch")
    return address


def _queue_for_write(store: JsonStore) -> dict[str, Any]:
    queue = store.read("commands.json", {"pending": None, "last": None})
    if not isinstance(queue, dict):
        queue = {"pending": None, "last": None}
    command = queue.get("pending")
    if not isinstance(command, dict) or command.get("state") != "pending":
        return queue

    now = int(time.time())
    if int(command.get("expires_at", 0) or 0) > now:
        raise GateError("command_pending")

    command["state"] = "expired"
    queue["last"] = command
    queue["pending"] = None
    store.write("commands.json", queue)
    store.append_activity({"type": "command_expired", "command_id": command.get("id", "")})
    return queue


def queue_activate(
    store: JsonStore,
    *,
    source_ip: str,
    ttl: int,
    endpoint_id: str | None = None,
    family: str | None = None,
    scope: str = "wg_ping",
    wan_name: str | None = None,
    wg_name: str | None = None,
) -> dict[str, Any]:
    """Queue one temporary authorization.

    New schema-2 callers provide endpoint_id/family/scope. Schema-1 callers may
    continue to provide wan_name/wg_name while the VPS is upgraded first.
    """
    if ttl not in ALLOWED_TTLS:
        raise GateError("invalid_ttl")
    if scope not in ALLOWED_SCOPES:
        raise GateError("invalid_scope")

    if endpoint_id:
        endpoint = endpoint_by_id(store, endpoint_id)
        endpoint_family = str(endpoint.get("family"))
        address = _source_address(source_ip, family or endpoint_family)
        if endpoint_family != ("ipv4" if address.version == 4 else "ipv6"):
            raise GateError("endpoint_family_mismatch")
        if family and family != endpoint_family:
            raise GateError("endpoint_family_mismatch")
        if endpoint.get("reachability") not in {"direct", "mapped", "private"}:
            raise GateError("endpoint_not_reachable")

        inventory = normalize_inventory(store)
        caps = inventory.get("capabilities") if isinstance(inventory, dict) else {}
        if endpoint_family == "ipv6" and isinstance(caps, dict) and not bool(caps.get("gate_ipv6", False)):
            raise GateError("ipv6_gate_unavailable")

        agent_schema = _agent_schema(store)
        advanced = (
            endpoint_family == "ipv6"
            or scope != "wg_ping"
            or endpoint.get("provider") != "native"
            or endpoint.get("reachability") == "private"
        )
        if advanced and agent_schema < 2:
            raise GateError("agent_upgrade_required")

        now = int(time.time())
        command = {
            "schema": 2,
            "id": secrets.token_hex(16),
            "action": "activate",
            "created_at": now,
            "expires_at": now + 60,
            "source_ip": str(address),
            "family": endpoint_family,
            "scope": scope,
            "endpoint_id": str(endpoint["id"]),
            "provider": str(endpoint.get("provider", "native")),
            "reachability": str(endpoint.get("reachability", "")),
            "wan": str(endpoint.get("wan", "")),
            "device": str(endpoint["device"]),
            "wireguard": str(endpoint["wireguard"]),
            "wg_port": int(endpoint["local_port"]),
            "external_address": str(endpoint.get("external_address", "")),
            "external_port": int(endpoint.get("external_port", endpoint["local_port"])),
            "ttl": ttl,
            "state": "pending",
        }
    else:
        # Compatibility with the current v0.2.x server/browser contract.
        address = _source_address(source_ip, "ipv4")
        if not wan_name or not wg_name:
            raise GateError("endpoint_required")
        wan = public_wan(store, wan_name)
        wg = wireguard_interface(store, wg_name)
        now = int(time.time())
        command = {
            "schema": 1,
            "id": secrets.token_hex(16),
            "action": "activate",
            "created_at": now,
            "expires_at": now + 60,
            "source_ip": str(address),
            "family": "ipv4",
            "scope": "wg_ping",
            "wan": wan_name,
            "device": str(wan["device"]),
            "wireguard": wg_name,
            "wg_port": int(wg["listen_port"]),
            "ttl": ttl,
            "state": "pending",
        }

    with QUEUE_LOCK:
        _queue_for_write(store)
        store.write("commands.json", {"pending": command, "last": None})
        store.append_activity(
            {
                "type": "gate_requested",
                "source_ip": command["source_ip"],
                "family": command["family"],
                "scope": command["scope"],
                "wan": command.get("wan", ""),
                "wireguard": command.get("wireguard", ""),
                "endpoint_id": command.get("endpoint_id", ""),
                "ttl": ttl,
            }
        )
    return command


def queue_close(store: JsonStore, *, source_ip: str) -> dict[str, Any]:
    address = _source_address(source_ip)
    now = int(time.time())
    command = {
        "schema": 2,
        "id": secrets.token_hex(16),
        "action": "close",
        "created_at": now,
        "expires_at": now + 60,
        "source_ip": str(address),
        "family": "ipv4" if address.version == 4 else "ipv6",
        "state": "pending",
    }
    with QUEUE_LOCK:
        _queue_for_write(store)
        store.write("commands.json", {"pending": command, "last": None})
        store.append_activity({"type": "gate_close_requested", "source_ip": str(address)})
    return command


def pull_command(store: JsonStore) -> dict[str, Any] | None:
    with QUEUE_LOCK:
        queue = store.read("commands.json", {"pending": None, "last": None})
        if not isinstance(queue, dict):
            return None
        command = queue.get("pending")
        if not isinstance(command, dict):
            return None
        if command.get("state") != "pending":
            return None
        if int(command.get("expires_at", 0)) <= int(time.time()):
            command["state"] = "expired"
            queue["last"] = command
            queue["pending"] = None
            store.write("commands.json", queue)
            store.append_activity({"type": "command_expired", "command_id": command.get("id", "")})
            return None
        return command


def ack_command(store: JsonStore, command_id: str, ok: bool, detail: str = "") -> bool:
    with QUEUE_LOCK:
        queue = store.read("commands.json", {"pending": None, "last": None})
        if not isinstance(queue, dict):
            return False
        command = queue.get("pending")
        if not isinstance(command, dict) or command.get("id") != command_id:
            return False
        command["state"] = "done" if ok else "failed"
        command["acked_at"] = int(time.time())
        command["detail"] = detail[:240]
        queue["last"] = command
        queue["pending"] = None
        store.write("commands.json", queue)
        store.append_activity(
            {
                "type": "command_done" if ok else "command_failed",
                "command_id": command_id,
                "action": command.get("action"),
                "detail": detail[:120],
            }
        )
        return True


def gate_view(store: JsonStore) -> dict[str, Any]:
    queue = store.read("commands.json", {"pending": None, "last": None})
    agent = store.read("agent-status.json", {})
    return {
        "queue": queue if isinstance(queue, dict) else {"pending": None, "last": None},
        "agent": agent if isinstance(agent, dict) else {},
    }
