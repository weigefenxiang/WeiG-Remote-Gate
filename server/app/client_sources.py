from __future__ import annotations

import hashlib
import ipaddress
import time
from typing import Any

from .store import JsonStore

SOURCE_TTL = 10 * 60
CANDIDATE_TTL = 5 * 60
IPV6_GLOBAL_UNICAST = ipaddress.ip_network("2000::/3")


def _session_key(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _globally_reachable_unicast(value: object, version: int | None = None) -> bool:
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


def _state(store: JsonStore, current: int) -> tuple[dict[str, Any], dict[str, Any]]:
    state = store.read("client-sources.json", {})
    if not isinstance(state, dict): state = {}
    sessions = state.setdefault("sessions", {})
    if not isinstance(sessions, dict): sessions = {}; state["sessions"] = sessions
    for sid, record in list(sessions.items()):
        if not isinstance(record, dict): sessions.pop(sid, None); continue
        families = record.get("families")
        if not isinstance(families, dict): sessions.pop(sid, None); continue
        for family, item in list(families.items()):
            if not isinstance(item, dict) or int(item.get("expires_at", 0) or 0) <= current: families.pop(family, None)
        if not families: sessions.pop(sid, None)
    return state, sessions


def _global_address(value: str, family: str | None = None):
    address = ipaddress.ip_address(str(value or "").strip())
    expected = family or ("ipv4" if address.version == 4 else "ipv6")
    if expected not in {"ipv4", "ipv6"}: raise ValueError("invalid_family")
    if (expected == "ipv4" and address.version != 4) or (expected == "ipv6" and address.version != 6): raise ValueError("source_family_mismatch")
    if not _globally_reachable_unicast(address, address.version): raise ValueError("public_source_required")
    return address


def _record(store: JsonStore, session_token: str, source_ip: str, *, source: str, confidence: str, now: int | None = None, ttl: int = SOURCE_TTL, keep_verified: bool = False) -> dict[str, Any]:
    address = _global_address(source_ip)
    current = int(time.time()) if now is None else int(now)
    family = "ipv4" if address.version == 4 else "ipv6"
    state, sessions = _state(store, current)
    record = sessions.setdefault(_session_key(session_token), {"families": {}})
    families = record.setdefault("families", {})
    existing = families.get(family)
    if keep_verified and isinstance(existing, dict) and existing.get("confidence") == "verified" and int(existing.get("expires_at", 0) or 0) > current:
        return {"family": family, **existing}
    families[family] = {"address": str(address), "observed_at": current, "expires_at": current + max(30, min(int(ttl), SOURCE_TTL)), "source": source, "confidence": confidence}
    store.write("client-sources.json", state)
    return {"family": family, **families[family]}


def observe_source(store: JsonStore, session_token: str, source_ip: str, *, now: int | None = None, ttl: int = SOURCE_TTL) -> dict[str, Any]:
    return _record(store, session_token, source_ip, source="cloudflare", confidence="verified", now=now, ttl=ttl)


def observe_candidate(store: JsonStore, session_token: str, source_ip: str, family: str, *, now: int | None = None) -> dict[str, Any]:
    address = _global_address(source_ip, family)
    return _record(store, session_token, str(address), source="carrier_probe", confidence="candidate", now=now, ttl=CANDIDATE_TTL, keep_verified=True)


def trusted_sources(store: JsonStore, session_token: str, *, now: int | None = None) -> dict[str, dict[str, Any]]:
    current = int(time.time()) if now is None else int(now)
    state = store.read("client-sources.json", {})
    sessions = state.get("sessions") if isinstance(state, dict) else None
    record = sessions.get(_session_key(session_token)) if isinstance(sessions, dict) else None
    families = record.get("families") if isinstance(record, dict) else None
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(families, dict): return result
    for family in ("ipv4", "ipv6"):
        item = families.get(family)
        if not isinstance(item, dict) or int(item.get("expires_at", 0) or 0) <= current: continue
        try: address = _global_address(str(item.get("address") or ""), family)
        except ValueError: continue
        confidence = str(item.get("confidence") or "")
        if confidence not in {"verified", "candidate"}: continue
        result[family] = {"address": str(address), "observed_at": int(item.get("observed_at", 0) or 0), "expires_at": int(item.get("expires_at", 0) or 0), "source": str(item.get("source") or "unknown"), "confidence": confidence}
    return result


def source_record_for_family(store: JsonStore, session_token: str, family: str, *, now: int | None = None) -> dict[str, Any]:
    if family not in {"ipv4", "ipv6"}: raise ValueError("invalid_family")
    item = trusted_sources(store, session_token, now=now).get(family)
    if not item: raise ValueError("client_source_not_observed")
    return item


def source_for_family(store: JsonStore, session_token: str, family: str, *, now: int | None = None) -> str:
    return str(source_record_for_family(store, session_token, family, now=now)["address"])


def delete_sources(store: JsonStore, session_token: str) -> None:
    state = store.read("client-sources.json", {})
    sessions = state.get("sessions") if isinstance(state, dict) else None
    if not isinstance(sessions, dict): return
    sessions.pop(_session_key(session_token), None); state["sessions"] = sessions; store.write("client-sources.json", state)


def observe_network_probe(*args, **kwargs) -> dict[str, Any]: raise ValueError("legacy_source_probe_disabled")
def observe_ipv4_probe(*args, **kwargs) -> dict[str, Any]: raise ValueError("legacy_source_probe_disabled")
