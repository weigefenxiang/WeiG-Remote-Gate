from __future__ import annotations

import hashlib
import ipaddress
from typing import Any

from .store import JsonStore


def _safe_ip(value: object) -> str | None:
    try:
        return str(ipaddress.ip_address(str(value or "").strip()))
    except ValueError:
        return None


def _address_kind(value: str) -> str:
    addr = ipaddress.ip_address(value)
    if addr.version == 4:
        return "public" if addr.is_global else "private"
    return "global" if addr.is_global else "non_global"


def _endpoint_id(parts: list[str]) -> str:
    raw = "|".join(parts).encode("utf-8")
    return "ep_" + hashlib.sha256(raw).hexdigest()[:20]


def normalize_inventory(store: JsonStore) -> dict[str, Any]:
    """Return schema-2 inventory, synthesizing it from schema-1 state when needed."""
    state = store.read("inventory-v2.json", {})
    if isinstance(state, dict) and int(state.get("schema", 0) or 0) == 2:
        wans = state.get("wans")
        if isinstance(wans, list):
            return state

    legacy = store.read("current.json", {"schema": 1, "interfaces": {}})
    interfaces = legacy.get("interfaces") if isinstance(legacy, dict) else None
    wans: list[dict[str, Any]] = []
    if isinstance(interfaces, dict):
        for name, item in interfaces.items():
            if not isinstance(item, dict) or not item.get("active"):
                continue
            address = _safe_ip(item.get("ip"))
            device = str(item.get("device") or "")
            if not address or not device:
                continue
            family = "ipv4" if ipaddress.ip_address(address).version == 4 else "ipv6"
            record: dict[str, Any] = {
                "name": str(name),
                "device": device,
                "logical_interfaces": [str(name)],
                "up": True,
                "default_route_v4": family == "ipv4",
                "default_route_v6": family == "ipv6",
                "ipv4": [],
                "ipv6": [],
            }
            record[family].append({"address": address, "kind": _address_kind(address)})
            wans.append(record)
    return {"schema": 2, "compat_from": 1, "wans": wans, "natmap": [], "capabilities": {}}


def validate_inventory_v2(data: object) -> dict[str, Any]:
    if not isinstance(data, dict) or int(data.get("schema", 0) or 0) != 2:
        raise ValueError("schema2_required")
    raw_wans = data.get("wans")
    if not isinstance(raw_wans, list) or len(raw_wans) > 64:
        raise ValueError("invalid_wans")

    clean_wans: list[dict[str, Any]] = []
    seen_devices: set[str] = set()
    for raw in raw_wans:
        if not isinstance(raw, dict):
            raise ValueError("invalid_wan")
        name = str(raw.get("name") or "").strip()
        device = str(raw.get("device") or "").strip()
        if not name or len(name) > 64 or not device or len(device) > 128:
            raise ValueError("invalid_wan")
        if device in seen_devices:
            raise ValueError("duplicate_wan_device")
        seen_devices.add(device)

        clean: dict[str, Any] = {
            "name": name,
            "device": device,
            "logical_interfaces": [
                str(x)[:64] for x in raw.get("logical_interfaces", []) if isinstance(x, str) and x
            ][:16],
            "up": bool(raw.get("up")),
            "default_route_v4": bool(raw.get("default_route_v4")),
            "default_route_v6": bool(raw.get("default_route_v6")),
            "ipv4": [],
            "ipv6": [],
        }
        for family, version in (("ipv4", 4), ("ipv6", 6)):
            values = raw.get(family, [])
            if not isinstance(values, list) or len(values) > 32:
                raise ValueError("invalid_addresses")
            for entry in values:
                value = entry.get("address") if isinstance(entry, dict) else entry
                address = _safe_ip(value)
                if not address or ipaddress.ip_address(address).version != version:
                    raise ValueError("invalid_address")
                clean[family].append({"address": address, "kind": _address_kind(address)})
        clean_wans.append(clean)

    raw_natmap = data.get("natmap", [])
    if not isinstance(raw_natmap, list) or len(raw_natmap) > 64:
        raise ValueError("invalid_natmap")
    clean_natmap: list[dict[str, Any]] = []
    for raw in raw_natmap:
        if not isinstance(raw, dict):
            raise ValueError("invalid_natmap")
        external = _safe_ip(raw.get("external_address"))
        if not external or ipaddress.ip_address(external).version != 4 or not ipaddress.ip_address(external).is_global:
            continue
        try:
            external_port = int(raw.get("external_port", 0))
            local_port = int(raw.get("local_port", 0))
        except (TypeError, ValueError):
            continue
        if not (1 <= external_port <= 65535 and 1 <= local_port <= 65535):
            continue
        device = str(raw.get("device") or "").strip()
        wan = str(raw.get("wan") or "").strip()
        if not device or not wan:
            continue
        clean_natmap.append({
            "wan": wan[:64],
            "device": device[:128],
            "external_address": external,
            "external_port": external_port,
            "local_port": local_port,
        })

    caps = data.get("capabilities") if isinstance(data.get("capabilities"), dict) else {}
    return {
        "schema": 2,
        "generated_at": int(data.get("generated_at", 0) or 0),
        "wans": clean_wans,
        "natmap": clean_natmap,
        "capabilities": {
            "gate_ipv4": bool(caps.get("gate_ipv4", True)),
            "gate_ipv6": bool(caps.get("gate_ipv6", False)),
            "control_ipv4": bool(caps.get("control_ipv4", True)),
            "control_ipv6": bool(caps.get("control_ipv6", False)),
            "natmap": bool(caps.get("natmap", bool(clean_natmap))),
        },
    }


def _wireguards(agent: object) -> list[dict[str, Any]]:
    if not isinstance(agent, dict):
        return []
    result = []
    for raw in agent.get("wireguard", []) if isinstance(agent.get("wireguard"), list) else []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        try:
            port = int(raw.get("listen_port", 0))
        except (TypeError, ValueError):
            continue
        if name and 1 <= port <= 65535:
            result.append({"name": name, "listen_port": port})
    return result


def build_endpoints(store: JsonStore) -> list[dict[str, Any]]:
    inventory = normalize_inventory(store)
    agent = store.read("agent-status.json", {})
    wireguards = _wireguards(agent)
    endpoints: list[dict[str, Any]] = []

    for wan in inventory.get("wans", []):
        if not isinstance(wan, dict) or not wan.get("up"):
            continue
        name = str(wan.get("name") or "")
        device = str(wan.get("device") or "")
        for wg in wireguards:
            port = int(wg["listen_port"])
            for entry in wan.get("ipv4", []):
                if not isinstance(entry, dict):
                    continue
                address = _safe_ip(entry.get("address"))
                if not address:
                    continue
                direct = ipaddress.ip_address(address).is_global
                endpoints.append({
                    "id": _endpoint_id(["native", name, device, "ipv4", address, str(port), wg["name"]]),
                    "wan": name,
                    "device": device,
                    "family": "ipv4",
                    "provider": "native",
                    "external_address": address,
                    "external_port": port,
                    "local_port": port,
                    "wireguard": wg["name"],
                    "reachability": "direct" if direct else "private",
                    "priority": 0 if direct else 90,
                })
            for entry in wan.get("ipv6", []):
                if not isinstance(entry, dict):
                    continue
                address = _safe_ip(entry.get("address"))
                if not address:
                    continue
                direct = ipaddress.ip_address(address).is_global
                endpoints.append({
                    "id": _endpoint_id(["native", name, device, "ipv6", address, str(port), wg["name"]]),
                    "wan": name,
                    "device": device,
                    "family": "ipv6",
                    "provider": "native",
                    "external_address": address,
                    "external_port": port,
                    "local_port": port,
                    "wireguard": wg["name"],
                    "reachability": "direct" if direct else "non_global",
                    "priority": 10 if direct else 95,
                })

    for mapping in inventory.get("natmap", []):
        if not isinstance(mapping, dict):
            continue
        for wg in wireguards:
            if int(mapping.get("local_port", 0) or 0) != int(wg["listen_port"]):
                continue
            endpoints.append({
                "id": _endpoint_id([
                    "natmap", str(mapping.get("wan")), str(mapping.get("device")),
                    str(mapping.get("external_address")), str(mapping.get("external_port")),
                    str(mapping.get("local_port")), wg["name"],
                ]),
                "wan": str(mapping.get("wan")),
                "device": str(mapping.get("device")),
                "family": "ipv4",
                "provider": "natmap",
                "external_address": str(mapping.get("external_address")),
                "external_port": int(mapping.get("external_port")),
                "local_port": int(mapping.get("local_port")),
                "wireguard": wg["name"],
                "reachability": "mapped",
                "priority": 20,
            })

    endpoints.sort(key=lambda item: (
        int(item.get("priority", 999)),
        str(item.get("wan", "")),
        str(item.get("wireguard", "")),
        str(item.get("external_address", "")),
    ))
    return endpoints


def endpoint_by_id(store: JsonStore, endpoint_id: str) -> dict[str, Any]:
    for endpoint in build_endpoints(store):
        if endpoint.get("id") == endpoint_id:
            return endpoint
    raise KeyError(endpoint_id)
