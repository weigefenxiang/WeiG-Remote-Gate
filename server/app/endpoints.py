from __future__ import annotations

import hashlib
import ipaddress
import time
from typing import Any

from .store import JsonStore


WAN_EGRESS_TTL = 10 * 60
IPV6_GLOBAL_UNICAST = ipaddress.ip_network("2000::/3")
ALLOWED_SERVICE_TYPES = {"wireguard"}
ALLOWED_TRANSPORTS = {"udp"}


def _safe_ip(value: object) -> str | None:
    try:
        return str(ipaddress.ip_address(str(value or "").strip()))
    except ValueError:
        return None


def _safe_name(value: object, *, maximum: int = 128) -> str:
    text = str(value or "").strip()
    if not text or len(text) > maximum:
        return ""
    if any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.:@+-" for ch in text):
        return ""
    return text


def _safe_port(value: object) -> int | None:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return None
    return port if 1 <= port <= 65535 else None


def _strict_bool(record: dict[str, Any], key: str, default: bool) -> bool:
    if key not in record:
        return default
    value = record.get(key)
    if not isinstance(value, bool):
        raise ValueError("invalid_boolean")
    return value


def is_globally_reachable_unicast(value: object, *, version: int | None = None) -> bool:
    try:
        address = ipaddress.ip_address(str(value or "").strip())
    except ValueError:
        return False
    if version is not None and address.version != version:
        return False
    if not address.is_global or address.is_multicast:
        return False
    if address.version == 6 and address not in IPV6_GLOBAL_UNICAST:
        return False
    return True


def _address_kind(value: str) -> str:
    addr = ipaddress.ip_address(value)
    if addr.version == 4:
        return "public" if is_globally_reachable_unicast(addr, version=4) else "private"
    return "global" if is_globally_reachable_unicast(addr, version=6) else "non_global"


def _endpoint_id(parts: list[str]) -> str:
    raw = "|".join(parts).encode("utf-8")
    return "ep_" + hashlib.sha256(raw).hexdigest()[:20]


def observe_wan_egress(
    store: JsonStore,
    device: str,
    source_ip: str,
    *,
    now: int | None = None,
) -> dict[str, Any]:
    address = ipaddress.ip_address(source_ip)
    if not is_globally_reachable_unicast(address, version=4):
        raise ValueError("public_ipv4_required")
    current = int(time.time()) if now is None else int(now)
    state = store.read("wan-egress-v4.json", {})
    if not isinstance(state, dict):
        state = {}
    records = state.setdefault("devices", {})
    if not isinstance(records, dict):
        records = {}
        state["devices"] = records
    records[str(device)] = {
        "address": str(address),
        "observed_at": current,
        "expires_at": current + WAN_EGRESS_TTL,
    }
    store.write("wan-egress-v4.json", state)
    return dict(records[str(device)])


def wan_egress_for_device(
    store: JsonStore,
    device: str,
    *,
    now: int | None = None,
) -> dict[str, Any] | None:
    current = int(time.time()) if now is None else int(now)
    state = store.read("wan-egress-v4.json", {})
    records = state.get("devices") if isinstance(state, dict) else None
    item = records.get(str(device)) if isinstance(records, dict) else None
    if not isinstance(item, dict) or int(item.get("expires_at", 0) or 0) <= current:
        return None
    address = _safe_ip(item.get("address"))
    if not address or not is_globally_reachable_unicast(address, version=4):
        return None
    return {
        "address": address,
        "observed_at": int(item.get("observed_at", 0) or 0),
        "expires_at": int(item.get("expires_at", 0) or 0),
    }


def _clean_wans(data: object) -> tuple[list[dict[str, Any]], bool]:
    if not isinstance(data, list) or len(data) > 64:
        raise ValueError("invalid_wans")
    clean_wans: list[dict[str, Any]] = []
    seen_devices: set[str] = set()
    has_global_v6 = False
    for raw in data:
        if not isinstance(raw, dict):
            raise ValueError("invalid_wan")
        name = _safe_name(raw.get("name"), maximum=64)
        device = _safe_name(raw.get("device"), maximum=128)
        if not name or not device:
            raise ValueError("invalid_wan")
        if device in seen_devices:
            raise ValueError("duplicate_wan_device")
        seen_devices.add(device)
        logical: list[str] = []
        for value in raw.get("logical_interfaces", []) if isinstance(raw.get("logical_interfaces"), list) else []:
            item = _safe_name(value, maximum=64)
            if item and item not in logical:
                logical.append(item)
            if len(logical) >= 16:
                break
        clean: dict[str, Any] = {
            "name": name,
            "device": device,
            "logical_interfaces": logical,
            "up": _strict_bool(raw, "up", False),
            "default_route_v4": _strict_bool(raw, "default_route_v4", False),
            "default_route_v6": _strict_bool(raw, "default_route_v6", False),
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
                if family == "ipv6" and not is_globally_reachable_unicast(address, version=6):
                    continue
                if family == "ipv6":
                    has_global_v6 = True
                clean[family].append({"address": address, "kind": _address_kind(address)})
        clean_wans.append(clean)
    return clean_wans, has_global_v6


def validate_inventory_v2(data: object) -> dict[str, Any]:
    """Validate the legacy schema-2 contract during rolling upgrades."""
    if not isinstance(data, dict) or int(data.get("schema", 0) or 0) != 2:
        raise ValueError("schema2_required")
    clean_wans, has_global_v6 = _clean_wans(data.get("wans"))
    known_wans = {(item["name"], item["device"]) for item in clean_wans if item["up"]}

    raw_natmap = data.get("natmap", [])
    if not isinstance(raw_natmap, list) or len(raw_natmap) > 64:
        raise ValueError("invalid_natmap")
    clean_natmap: list[dict[str, Any]] = []
    for raw in raw_natmap:
        if not isinstance(raw, dict):
            raise ValueError("invalid_natmap")
        external = _safe_ip(raw.get("external_address"))
        external_port = _safe_port(raw.get("external_port"))
        local_port = _safe_port(raw.get("local_port"))
        device = _safe_name(raw.get("device"), maximum=128)
        wan = _safe_name(raw.get("wan"), maximum=64)
        if not external or not is_globally_reachable_unicast(external, version=4):
            continue
        if external_port is None or local_port is None or not device or not wan:
            continue
        if (wan, device) not in known_wans:
            continue
        clean_natmap.append({
            "wan": wan,
            "device": device,
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
            "gate_ipv4": _strict_bool(caps, "gate_ipv4", True),
            "gate_ipv6": _strict_bool(caps, "gate_ipv6", False),
            "control_ipv4": _strict_bool(caps, "control_ipv4", True),
            "control_ipv6": _strict_bool(caps, "control_ipv6", False) and has_global_v6,
            "natmap": _strict_bool(caps, "natmap", bool(clean_natmap)),
        },
    }


def validate_inventory_v3(data: object) -> dict[str, Any]:
    if not isinstance(data, dict) or int(data.get("schema", 0) or 0) != 3:
        raise ValueError("schema3_required")
    clean_wans, has_global_v6 = _clean_wans(data.get("wans"))
    active_wans = {(item["name"], item["device"]) for item in clean_wans if item["up"]}

    raw_services = data.get("services", [])
    if not isinstance(raw_services, list) or len(raw_services) > 64:
        raise ValueError("invalid_services")
    services: list[dict[str, Any]] = []
    service_by_id: dict[str, dict[str, Any]] = {}
    for raw in raw_services:
        if not isinstance(raw, dict):
            raise ValueError("invalid_service")
        service_id = _safe_name(raw.get("id"), maximum=96)
        service_type = str(raw.get("type") or "").strip().lower()
        transport = str(raw.get("transport") or "").strip().lower()
        name = _safe_name(raw.get("name"), maximum=64)
        service_port = _safe_port(raw.get("service_port"))
        if (
            not service_id
            or service_id in service_by_id
            or service_type not in ALLOWED_SERVICE_TYPES
            or transport not in ALLOWED_TRANSPORTS
            or not name
            or service_port is None
        ):
            continue
        service = {
            "id": service_id,
            "type": service_type,
            "transport": transport,
            "name": name,
            "service_port": service_port,
        }
        services.append(service)
        service_by_id[service_id] = service

    raw_mappings = data.get("mappings", [])
    if not isinstance(raw_mappings, list) or len(raw_mappings) > 64:
        raise ValueError("invalid_mappings")
    mappings: list[dict[str, Any]] = []
    seen_mapping_keys: set[tuple[str, str, int, str]] = set()
    for raw in raw_mappings:
        if not isinstance(raw, dict):
            raise ValueError("invalid_mapping")
        wan = _safe_name(raw.get("wan"), maximum=64)
        device = _safe_name(raw.get("device"), maximum=128)
        family = str(raw.get("family") or "ipv4").strip().lower()
        transport = str(raw.get("transport") or "").strip().lower()
        external = _safe_ip(raw.get("external_address"))
        external_port = _safe_port(raw.get("external_port"))
        ingress_port = _safe_port(raw.get("ingress_port"))
        service_id = _safe_name(raw.get("service_id"), maximum=96)
        service = service_by_id.get(service_id)
        try:
            observed_at = max(0, int(raw.get("observed_at", 0) or 0))
        except (TypeError, ValueError):
            observed_at = 0
        if (
            not wan
            or not device
            or (wan, device) not in active_wans
            or family != "ipv4"
            or transport not in ALLOWED_TRANSPORTS
            or not external
            or not is_globally_reachable_unicast(external, version=4)
            or external_port is None
            or ingress_port is None
            or service is None
            or service["transport"] != transport
        ):
            continue
        key = (device, service_id, ingress_port, external)
        if key in seen_mapping_keys:
            continue
        seen_mapping_keys.add(key)
        mappings.append({
            "wan": wan,
            "device": device,
            "family": family,
            "transport": transport,
            "external_address": external,
            "external_port": external_port,
            "ingress_port": ingress_port,
            "service_id": service_id,
            "observed_at": observed_at,
        })

    caps = data.get("capabilities") if isinstance(data.get("capabilities"), dict) else {}
    return {
        "schema": 3,
        "generated_at": int(data.get("generated_at", 0) or 0),
        "wans": clean_wans,
        "services": services,
        "mappings": mappings,
        "capabilities": {
            "gate_ipv4": _strict_bool(caps, "gate_ipv4", True),
            "gate_ipv6": _strict_bool(caps, "gate_ipv6", False),
            "control_ipv4": _strict_bool(caps, "control_ipv4", True),
            "control_ipv6": _strict_bool(caps, "control_ipv6", False) and has_global_v6,
            "mapped_access": _strict_bool(caps, "mapped_access", bool(mappings)),
            "mapper_available": _strict_bool(caps, "mapper_available", False),
        },
    }


def normalize_inventory(store: JsonStore) -> dict[str, Any]:
    """Return the newest valid inventory while preserving legacy compatibility."""
    state3 = store.read("inventory-v3.json", {})
    if isinstance(state3, dict) and int(state3.get("schema", 0) or 0) == 3:
        try:
            return validate_inventory_v3(state3)
        except (TypeError, ValueError):
            pass

    state2 = store.read("inventory-v2.json", {})
    if isinstance(state2, dict) and int(state2.get("schema", 0) or 0) == 2:
        try:
            return validate_inventory_v2(state2)
        except (TypeError, ValueError):
            pass

    legacy = store.read("current.json", {"schema": 1, "interfaces": {}})
    interfaces = legacy.get("interfaces") if isinstance(legacy, dict) else None
    wans: list[dict[str, Any]] = []
    if isinstance(interfaces, dict):
        for name, item in interfaces.items():
            if not isinstance(item, dict) or not item.get("active"):
                continue
            address = _safe_ip(item.get("ip"))
            device = _safe_name(item.get("device"), maximum=128)
            if not address or not device:
                continue
            parsed = ipaddress.ip_address(address)
            family = "ipv4" if parsed.version == 4 else "ipv6"
            if family == "ipv6" and not is_globally_reachable_unicast(parsed, version=6):
                continue
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


def _wireguards(agent: object) -> list[dict[str, Any]]:
    if not isinstance(agent, dict):
        return []
    result = []
    for raw in agent.get("wireguard", []) if isinstance(agent.get("wireguard"), list) else []:
        if not isinstance(raw, dict):
            continue
        name = _safe_name(raw.get("name"), maximum=64)
        port = _safe_port(raw.get("listen_port"))
        if name and port is not None:
            result.append({"name": name, "listen_port": port})
    return result


def _service_records(inventory: dict[str, Any], agent: object) -> list[dict[str, Any]]:
    if int(inventory.get("schema", 0) or 0) == 3:
        values = inventory.get("services")
        if isinstance(values, list):
            return [dict(item) for item in values if isinstance(item, dict)]
    return [
        {
            "id": f"wg.{item['name']}",
            "type": "wireguard",
            "transport": "udp",
            "name": item["name"],
            "service_port": item["listen_port"],
        }
        for item in _wireguards(agent)
    ]


def build_endpoints(store: JsonStore) -> list[dict[str, Any]]:
    inventory = normalize_inventory(store)
    agent = store.read("agent-status.json", {})
    services = _service_records(inventory, agent)
    wireguard_services = [item for item in services if item.get("type") == "wireguard" and item.get("transport") == "udp"]
    service_by_id = {str(item.get("id")): item for item in services if item.get("id")}
    endpoints: list[dict[str, Any]] = []

    for wan in inventory.get("wans", []):
        if not isinstance(wan, dict) or not wan.get("up"):
            continue
        name = str(wan.get("name") or "")
        device = str(wan.get("device") or "")
        local_v4: list[str] = []
        has_direct_v4 = False
        for entry in wan.get("ipv4", []):
            if not isinstance(entry, dict):
                continue
            address = _safe_ip(entry.get("address"))
            if not address:
                continue
            local_v4.append(address)
            if is_globally_reachable_unicast(address, version=4):
                has_direct_v4 = True

        egress = None if has_direct_v4 else wan_egress_for_device(store, device)

        for service in wireguard_services:
            port = int(service["service_port"])
            service_id = str(service["id"])
            wireguard = str(service["name"])
            for address in local_v4:
                direct = is_globally_reachable_unicast(address, version=4)
                endpoints.append({
                    "id": _endpoint_id(["direct", name, device, "ipv4", address, str(port), service_id]),
                    "wan": name,
                    "device": device,
                    "family": "ipv4",
                    "access_method": "direct",
                    "provider": "native",
                    "transport": "udp",
                    "external_address": address,
                    "external_port": port,
                    "ingress_port": port,
                    "service_port": port,
                    "service_id": service_id,
                    "service_type": "wireguard",
                    "wireguard": wireguard,
                    "reachability": "direct" if direct else "private",
                    "priority": 0 if direct else 90,
                })

            if egress:
                endpoints.append({
                    "id": _endpoint_id(["egress_probe", name, device, str(egress["address"]), str(port), service_id]),
                    "wan": name,
                    "device": device,
                    "family": "ipv4",
                    "access_method": "direct",
                    "provider": "egress_probe",
                    "transport": "udp",
                    "external_address": str(egress["address"]),
                    "external_port": port,
                    "ingress_port": port,
                    "service_port": port,
                    "service_id": service_id,
                    "service_type": "wireguard",
                    "wireguard": wireguard,
                    "reachability": "egress_probe",
                    "priority": 30,
                    "observed_at": int(egress["observed_at"]),
                })

            for entry in wan.get("ipv6", []):
                if not isinstance(entry, dict):
                    continue
                address = _safe_ip(entry.get("address"))
                if not address or not is_globally_reachable_unicast(address, version=6):
                    continue
                endpoints.append({
                    "id": _endpoint_id(["direct", name, device, "ipv6", address, str(port), service_id]),
                    "wan": name,
                    "device": device,
                    "family": "ipv6",
                    "access_method": "direct",
                    "provider": "native",
                    "transport": "udp",
                    "external_address": address,
                    "external_port": port,
                    "ingress_port": port,
                    "service_port": port,
                    "service_id": service_id,
                    "service_type": "wireguard",
                    "wireguard": wireguard,
                    "reachability": "direct",
                    "priority": 10,
                })

    if int(inventory.get("schema", 0) or 0) == 3:
        for mapping in inventory.get("mappings", []):
            if not isinstance(mapping, dict):
                continue
            service = service_by_id.get(str(mapping.get("service_id") or ""))
            if not service or service.get("type") != "wireguard" or service.get("transport") != "udp":
                continue
            endpoints.append({
                "id": _endpoint_id([
                    "mapped", str(mapping.get("wan")), str(mapping.get("device")),
                    str(mapping.get("external_address")), str(mapping.get("external_port")),
                    str(mapping.get("ingress_port")), str(mapping.get("service_id")),
                ]),
                "wan": str(mapping.get("wan")),
                "device": str(mapping.get("device")),
                "family": "ipv4",
                "access_method": "mapped",
                "provider": "mapping",
                "transport": "udp",
                "external_address": str(mapping.get("external_address")),
                "external_port": int(mapping.get("external_port")),
                "ingress_port": int(mapping.get("ingress_port")),
                "service_port": int(service.get("service_port")),
                "service_id": str(service.get("id")),
                "service_type": str(service.get("type")),
                "wireguard": str(service.get("name")),
                "reachability": "mapped",
                "priority": 20,
                "observed_at": int(mapping.get("observed_at", 0) or 0),
            })
    else:
        # Rolling-upgrade compatibility for old schema-2 agents. New 0.3.17
        # agents do not emit or depend on NATMap records.
        wireguards = _wireguards(agent)
        for mapping in inventory.get("natmap", []):
            if not isinstance(mapping, dict):
                continue
            for wg in wireguards:
                if int(mapping.get("local_port", 0) or 0) != int(wg["listen_port"]):
                    continue
                endpoints.append({
                    "id": _endpoint_id([
                        "legacy-mapped", str(mapping.get("wan")), str(mapping.get("device")),
                        str(mapping.get("external_address")), str(mapping.get("external_port")),
                        str(mapping.get("local_port")), wg["name"],
                    ]),
                    "wan": str(mapping.get("wan")),
                    "device": str(mapping.get("device")),
                    "family": "ipv4",
                    "access_method": "mapped",
                    "provider": "legacy_mapping",
                    "transport": "udp",
                    "external_address": str(mapping.get("external_address")),
                    "external_port": int(mapping.get("external_port")),
                    "ingress_port": int(mapping.get("local_port")),
                    "service_port": int(mapping.get("local_port")),
                    "service_id": f"wg.{wg['name']}",
                    "service_type": "wireguard",
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
