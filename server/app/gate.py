from __future__ import annotations

import ipaddress
import secrets
import threading
import time
from typing import Any

from .endpoints import endpoint_by_id, normalize_inventory
from .store import JsonStore


PRESET_TTLS = {60, 300, 900, 1800}
CUSTOM_TTL_MIN = 1800
CUSTOM_TTL_MAX = 12 * 60 * 60
CUSTOM_TTL_STEP = 1800
ALLOWED_SCOPES = {"wg", "wg_ping"}
ALLOWED_EGRESS_MODES = {"none", "ipv4", "ipv6", "dual"}
QUEUE_LOCK = threading.RLock()


class GateError(ValueError):
    pass


def valid_ttl(ttl: int) -> bool:
    if ttl in PRESET_TTLS:
        return True
    return CUSTOM_TTL_MIN <= ttl <= CUSTOM_TTL_MAX and ttl % CUSTOM_TTL_STEP == 0


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


def _wan_has_global_ipv6(item: dict[str, Any]) -> bool:
    values = item.get("ipv6")
    return isinstance(values, list) and any(
        isinstance(entry, dict) and entry.get("kind") == "global" and entry.get("address")
        for entry in values
    )


def egress_wan(store: JsonStore, name: str | None, mode: str = "ipv4") -> str:
    selected = str(name or "").strip()
    if not selected:
        return ""
    selected_mode = str(mode or "").strip()
    if selected_mode not in {"ipv4", "ipv6", "dual"}:
        raise GateError("invalid_egress_mode")
    inventory = normalize_inventory(store)
    for item in inventory.get("wans", []) if isinstance(inventory, dict) else []:
        if not isinstance(item, dict) or str(item.get("name") or "") != selected:
            continue
        if not item.get("up"):
            raise GateError("egress_wan_unavailable")
        if selected_mode in {"ipv4", "dual"} and not item.get("default_route_v4"):
            raise GateError("egress_ipv4_unavailable")
        if selected_mode in {"ipv6", "dual"}:
            if not item.get("default_route_v6") or not _wan_has_global_ipv6(item):
                raise GateError("egress_ipv6_unavailable")
        return selected
    raise GateError("egress_wan_unavailable")


def _egress_plan(
    store: JsonStore,
    *,
    egress_name: str | None,
    egress_names: dict[str, str] | None,
    mode: str,
) -> tuple[str, str, str, str]:
    selected_mode = str(mode or "").strip()
    if selected_mode not in ALLOWED_EGRESS_MODES:
        raise GateError("invalid_egress_mode")
    if selected_mode == "none":
        return "", "", "", ""

    requested = egress_names if isinstance(egress_names, dict) else {}
    if selected_mode == "dual" and requested:
        raw4 = str(requested.get("ipv4") or "").strip()
        raw6 = str(requested.get("ipv6") or "").strip()
        if bool(raw4) != bool(raw6):
            raise GateError("dual_egress_incomplete")
        if not raw4:
            return "", "", "", ""
        selected4 = egress_wan(store, raw4, "ipv4")
        selected6 = egress_wan(store, raw6, "ipv6")
        legacy = selected4 if selected4 == selected6 else ""
        return legacy, selected4, selected6, "dual"

    if selected_mode == "dual":
        shared = egress_wan(store, egress_name, "dual")
        if not shared:
            return "", "", "", ""
        return shared, shared, shared, "dual"

    if selected_mode == "ipv4":
        raw4 = str(requested.get("ipv4") or egress_name or "").strip()
        selected4 = egress_wan(store, raw4, "ipv4")
        return selected4, selected4, "", "ipv4" if selected4 else ""

    raw6 = str(requested.get("ipv6") or egress_name or "").strip()
    selected6 = egress_wan(store, raw6, "ipv6")
    return selected6, "", selected6, "ipv6" if selected6 else ""


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


def _empty_queue() -> dict[str, Any]:
    return {"pending": None, "next": [], "last": None}


def _rollback_command_for_expired_batch(command: dict[str, Any], now: int) -> dict[str, Any] | None:
    try:
        batch_count = int(command.get("batch_count", 1) or 1)
        batch_index = int(command.get("batch_index", 0) or 0)
        ttl = int(command.get("ttl", 60) or 60)
    except (TypeError, ValueError):
        return None
    batch_id = str(command.get("batch_id") or "").strip()
    if batch_count <= 1 or batch_index <= 0 or not batch_id:
        return None
    rollback_window = max(60, min(max(0, ttl), CUSTOM_TTL_MAX))
    return {
        "schema": 2,
        "id": secrets.token_hex(16),
        "action": "close",
        "created_at": now,
        "expires_at": now + rollback_window,
        "source_ip": str(command.get("source_ip") or ""),
        "family": str(command.get("family") or "ipv4"),
        "state": "pending",
        "rollback_for_batch": batch_id,
    }


def _archive_expired_pending(
    store: JsonStore,
    queue: dict[str, Any],
    command: dict[str, Any],
) -> dict[str, Any] | None:
    now = int(time.time())
    command["state"] = "expired"
    rollback = _rollback_command_for_expired_batch(command, now)
    queue["last"] = command
    queue["pending"] = rollback
    queue["next"] = []
    store.write("commands.json", queue)
    store.append_activity({"type": "command_expired", "command_id": command.get("id", "")})
    if rollback is not None:
        store.append_activity({
            "type": "batch_rollback_queued",
            "batch_id": rollback.get("rollback_for_batch", ""),
            "command_id": rollback.get("id", ""),
        })
    return rollback


def _queue_for_write(store: JsonStore) -> dict[str, Any]:
    queue = store.read("commands.json", _empty_queue())
    if not isinstance(queue, dict):
        queue = _empty_queue()
    if not isinstance(queue.get("next"), list):
        queue["next"] = []
    command = queue.get("pending")
    if not isinstance(command, dict) or command.get("state") != "pending":
        queue["pending"] = None
        return queue

    now = int(time.time())
    if int(command.get("expires_at", 0) or 0) > now:
        raise GateError("command_pending")

    rollback = _archive_expired_pending(store, queue, command)
    if rollback is not None:
        raise GateError("command_pending")
    return queue


def _activation_command(
    store: JsonStore,
    *,
    source_ip: str,
    ttl: int,
    endpoint_id: str | None = None,
    family: str | None = None,
    scope: str = "wg_ping",
    source_confidence: str = "verified",
    wan_name: str | None = None,
    wg_name: str | None = None,
    egress_name: str | None = None,
    egress_names: dict[str, str] | None = None,
    egress_mode: str = "ipv4",
    batch_id: str = "",
    batch_index: int = 0,
    batch_count: int = 1,
) -> dict[str, Any]:
    if not valid_ttl(ttl):
        raise GateError("invalid_ttl")
    if scope not in ALLOWED_SCOPES:
        raise GateError("invalid_scope")
    if source_confidence not in {"verified", "observed", "candidate"}:
        raise GateError("invalid_source_confidence")
    selected_egress, selected_egress4, selected_egress6, command_egress_mode = _egress_plan(
        store,
        egress_name=egress_name,
        egress_names=egress_names,
        mode=str(egress_mode or "ipv4"),
    )

    if endpoint_id:
        endpoint = endpoint_by_id(store, endpoint_id)
        endpoint_family = str(endpoint.get("family"))
        address = _source_address(source_ip, family or endpoint_family)
        if endpoint_family != ("ipv4" if address.version == 4 else "ipv6"):
            raise GateError("endpoint_family_mismatch")
        if family and family != endpoint_family:
            raise GateError("endpoint_family_mismatch")
        if endpoint.get("reachability") not in {"direct", "mapped", "egress_probe"}:
            raise GateError("endpoint_not_reachable")

        inventory = normalize_inventory(store)
        caps = inventory.get("capabilities") if isinstance(inventory, dict) else {}
        if endpoint_family == "ipv6" and isinstance(caps, dict) and not bool(caps.get("gate_ipv6", False)):
            raise GateError("ipv6_gate_unavailable")

        access_method = str(endpoint.get("access_method") or "direct")
        if access_method not in {"direct", "mapped"}:
            raise GateError("unsupported_access_method")
        transport = str(endpoint.get("transport") or "udp")
        if transport != "udp":
            raise GateError("unsupported_transport")
        service_type = str(endpoint.get("service_type") or "wireguard")
        if service_type != "wireguard":
            raise GateError("unsupported_service")
        try:
            ingress_port = int(endpoint.get("ingress_port", endpoint.get("local_port", 0)) or 0)
            service_port = int(endpoint.get("service_port", endpoint.get("local_port", 0)) or 0)
        except (TypeError, ValueError) as exc:
            raise GateError("invalid_endpoint_port") from exc
        if not 1 <= ingress_port <= 65535 or not 1 <= service_port <= 65535:
            raise GateError("invalid_endpoint_port")

        agent_schema = _agent_schema(store)
        advanced = (
            endpoint_family == "ipv6"
            or scope != "wg_ping"
            or access_method == "mapped"
            or endpoint.get("provider") != "native"
            or endpoint.get("reachability") == "egress_probe"
            or source_confidence == "candidate"
            or batch_count > 1
            or bool(selected_egress4 or selected_egress6)
        )
        if advanced and agent_schema < 2:
            raise GateError("agent_upgrade_required")
        if access_method == "mapped" and agent_schema < 3:
            raise GateError("agent_upgrade_required")

        now = int(time.time())
        command = {
            "schema": 3 if advanced else 2,
            "id": secrets.token_hex(16),
            "action": "activate",
            "created_at": now,
            "expires_at": now + 60,
            "source_ip": str(address),
            "source_confidence": source_confidence,
            "family": endpoint_family,
            "scope": scope,
            "endpoint_id": str(endpoint["id"]),
            "access_method": access_method,
            "provider": str(endpoint.get("provider", "native")),
            "reachability": str(endpoint.get("reachability", "")),
            "transport": transport,
            "wan": str(endpoint.get("wan", "")),
            "device": str(endpoint["device"]),
            "service_id": str(endpoint.get("service_id", "")),
            "service_type": service_type,
            "wireguard": str(endpoint["wireguard"]),
            "ingress_port": ingress_port,
            "service_port": service_port,
            "wg_port": service_port,
            "external_address": str(endpoint.get("external_address", "")),
            "external_port": int(endpoint.get("external_port", ingress_port)),
            "egress_wan": selected_egress,
            "egress_wan_ipv4": selected_egress4,
            "egress_wan_ipv6": selected_egress6,
            "egress_mode": command_egress_mode,
            "ttl": ttl,
            "state": "pending",
        }
        if batch_id:
            command.update({"batch_id": batch_id, "batch_index": batch_index, "batch_count": batch_count})
        return command

    address = _source_address(source_ip, "ipv4")
    if not wan_name or not wg_name:
        raise GateError("endpoint_required")
    wan = public_wan(store, wan_name)
    wg = wireguard_interface(store, wg_name)
    port = int(wg["listen_port"])
    now = int(time.time())
    return {
        "schema": 1,
        "id": secrets.token_hex(16),
        "action": "activate",
        "created_at": now,
        "expires_at": now + 60,
        "source_ip": str(address),
        "source_confidence": "verified",
        "family": "ipv4",
        "scope": "wg_ping",
        "access_method": "direct",
        "transport": "udp",
        "wan": wan_name,
        "device": str(wan["device"]),
        "service_id": f"wg.{wg_name}",
        "service_type": "wireguard",
        "wireguard": wg_name,
        "ingress_port": port,
        "service_port": port,
        "wg_port": port,
        "egress_wan": selected_egress,
        "egress_wan_ipv4": selected_egress4,
        "egress_wan_ipv6": selected_egress6,
        "egress_mode": command_egress_mode,
        "ttl": ttl,
        "state": "pending",
    }


def queue_activate(
    store: JsonStore,
    *,
    source_ip: str,
    ttl: int,
    endpoint_id: str | None = None,
    family: str | None = None,
    scope: str = "wg_ping",
    source_confidence: str = "verified",
    wan_name: str | None = None,
    wg_name: str | None = None,
    egress_name: str | None = None,
    egress_names: dict[str, str] | None = None,
    egress_mode: str | None = None,
) -> dict[str, Any]:
    selected_egress_mode = str(egress_mode or "").strip()
    if not selected_egress_mode:
        selected_egress_mode = family if family in {"ipv4", "ipv6"} else "ipv4"
    command = _activation_command(
        store,
        source_ip=source_ip,
        ttl=ttl,
        endpoint_id=endpoint_id,
        family=family,
        scope=scope,
        source_confidence=source_confidence,
        wan_name=wan_name,
        wg_name=wg_name,
        egress_name=egress_name,
        egress_names=egress_names,
        egress_mode=selected_egress_mode,
    )
    with QUEUE_LOCK:
        _queue_for_write(store)
        store.write("commands.json", {"pending": command, "next": [], "last": None})
        _append_gate_request(store, command)
    return command


def queue_activate_many(
    store: JsonStore,
    requests: list[dict[str, Any]],
    *,
    ttl: int,
    scope: str,
    egress_name: str | None = None,
    egress_names: dict[str, str] | None = None,
    egress_mode: str | None = None,
) -> dict[str, Any]:
    if not isinstance(requests, list) or not 1 <= len(requests) <= 2:
        raise GateError("invalid_families")
    families = [str(item.get("family") or "") for item in requests if isinstance(item, dict)]
    if len(families) != len(requests) or any(f not in {"ipv4", "ipv6"} for f in families) or len(set(families)) != len(families):
        raise GateError("invalid_families")

    selected_egress_mode = str(egress_mode or "").strip()
    if not selected_egress_mode:
        selected_egress_mode = "dual" if set(families) == {"ipv4", "ipv6"} else families[0]
    batch_id = secrets.token_hex(12)
    commands = [
        _activation_command(
            store,
            source_ip=str(item.get("source_ip") or ""),
            endpoint_id=str(item.get("endpoint_id") or ""),
            family=str(item.get("family") or ""),
            source_confidence=str(item.get("source_confidence") or "verified"),
            scope=scope,
            ttl=ttl,
            egress_name=egress_name,
            egress_names=egress_names,
            egress_mode=selected_egress_mode,
            batch_id=batch_id,
            batch_index=index,
            batch_count=len(requests),
        )
        for index, item in enumerate(requests)
    ]
    listeners = {
        (command.get("service_id"), int(command.get("service_port", command.get("wg_port", 0)) or 0))
        for command in commands
    }
    if len(listeners) != 1:
        raise GateError("wireguard_mismatch")

    with QUEUE_LOCK:
        _queue_for_write(store)
        store.write("commands.json", {"pending": commands[0], "next": commands[1:], "last": None})
        for command in commands:
            _append_gate_request(store, command)
    return {"batch_id": batch_id, "commands": commands, "pending": commands[0]}


def _append_gate_request(store: JsonStore, command: dict[str, Any]) -> None:
    store.append_activity(
        {
            "type": "gate_requested",
            "source_ip": command["source_ip"],
            "source_confidence": command.get("source_confidence", "verified"),
            "family": command["family"],
            "scope": command["scope"],
            "access_method": command.get("access_method", "direct"),
            "wan": command.get("wan", ""),
            "egress_wan": command.get("egress_wan", ""),
            "egress_wan_ipv4": command.get("egress_wan_ipv4", ""),
            "egress_wan_ipv6": command.get("egress_wan_ipv6", ""),
            "egress_mode": command.get("egress_mode", ""),
            "service_id": command.get("service_id", ""),
            "wireguard": command.get("wireguard", ""),
            "endpoint_id": command.get("endpoint_id", ""),
            "batch_id": command.get("batch_id", ""),
            "ttl": command["ttl"],
        }
    )


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
        store.write("commands.json", {"pending": command, "next": [], "last": None})
        store.append_activity({"type": "gate_close_requested", "source_ip": str(address)})
    return command


def pull_command(store: JsonStore) -> dict[str, Any] | None:
    with QUEUE_LOCK:
        queue = store.read("commands.json", _empty_queue())
        if not isinstance(queue, dict):
            return None
        command = queue.get("pending")
        if not isinstance(command, dict) or command.get("state") != "pending":
            return None
        if int(command.get("expires_at", 0)) <= int(time.time()):
            return _archive_expired_pending(store, queue, command)
        return command


def ack_command(store: JsonStore, command_id: str, ok: bool, detail: str = "") -> bool:
    with QUEUE_LOCK:
        queue = store.read("commands.json", _empty_queue())
        if not isinstance(queue, dict):
            return False
        command = queue.get("pending")
        if not isinstance(command, dict) or command.get("id") != command_id:
            return False
        command["state"] = "done" if ok else "failed"
        command["acked_at"] = int(time.time())
        command["detail"] = detail[:240]
        queue["last"] = command

        next_commands = queue.get("next") if isinstance(queue.get("next"), list) else []
        if ok and next_commands:
            next_command = next_commands.pop(0)
            if isinstance(next_command, dict):
                now = int(time.time())
                next_command["created_at"] = now
                next_command["expires_at"] = now + 60
                next_command["state"] = "pending"
                queue["pending"] = next_command
            else:
                queue["pending"] = None
            queue["next"] = next_commands
        else:
            queue["pending"] = None
            queue["next"] = []

        store.write("commands.json", queue)
        store.append_activity(
            {
                "type": "command_done" if ok else "command_failed",
                "command_id": command_id,
                "action": command.get("action"),
                "family": command.get("family", ""),
                "batch_id": command.get("batch_id", ""),
                "detail": detail[:120],
            }
        )
        return True


def gate_view(store: JsonStore) -> dict[str, Any]:
    with QUEUE_LOCK:
        queue = store.read("commands.json", _empty_queue())
        if not isinstance(queue, dict):
            queue = _empty_queue()
        pending = queue.get("pending")
        if isinstance(pending, dict) and pending.get("state") == "pending" and int(pending.get("expires_at", 0) or 0) <= int(time.time()):
            _archive_expired_pending(store, queue, pending)
    agent = store.read("agent-status.json", {})
    return {
        "queue": queue,
        "agent": agent if isinstance(agent, dict) else {},
    }
