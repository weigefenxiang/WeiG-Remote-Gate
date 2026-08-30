from __future__ import annotations

import ipaddress
import secrets
import time
from typing import Any

from .store import JsonStore


ALLOWED_TTLS = {60, 300, 900, 1800}


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
            port = int(item.get("listen_port", 0) or 0)
            if 1 <= port <= 65535:
                return item
    raise GateError("wireguard_unavailable")


def queue_activate(
    store: JsonStore,
    *,
    source_ip: str,
    wan_name: str,
    wg_name: str,
    ttl: int,
) -> dict[str, Any]:
    try:
        address = ipaddress.ip_address(source_ip)
    except ValueError as exc:
        raise GateError("invalid_source_ip") from exc
    if address.version != 4:
        raise GateError("ipv4_required")
    if ttl not in ALLOWED_TTLS:
        raise GateError("invalid_ttl")

    wan = public_wan(store, wan_name)
    wg = wireguard_interface(store, wg_name)
    now = int(time.time())
    command = {
        "id": secrets.token_hex(16),
        "action": "activate",
        "created_at": now,
        "expires_at": now + 60,
        "source_ip": str(address),
        "wan": wan_name,
        "device": str(wan["device"]),
        "wireguard": wg_name,
        "wg_port": int(wg["listen_port"]),
        "ttl": ttl,
        "state": "pending",
    }
    store.write("commands.json", {"pending": command, "last": None})
    store.append_activity(
        {
            "type": "gate_requested",
            "source_ip": str(address),
            "wan": wan_name,
            "wireguard": wg_name,
            "ttl": ttl,
        }
    )
    return command


def queue_close(store: JsonStore, *, source_ip: str) -> dict[str, Any]:
    now = int(time.time())
    command = {
        "id": secrets.token_hex(16),
        "action": "close",
        "created_at": now,
        "expires_at": now + 60,
        "source_ip": source_ip,
        "state": "pending",
    }
    store.write("commands.json", {"pending": command, "last": None})
    store.append_activity({"type": "gate_close_requested", "source_ip": source_ip})
    return command


def pull_command(store: JsonStore) -> dict[str, Any] | None:
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
