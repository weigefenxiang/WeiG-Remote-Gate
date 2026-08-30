from __future__ import annotations

import hashlib
import ipaddress
import time
from typing import Any

from .store import JsonStore


SOURCE_TTL = 10 * 60


def _session_key(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def observe_source(
    store: JsonStore,
    session_token: str,
    source_ip: str,
    *,
    now: int | None = None,
    ttl: int = SOURCE_TTL,
) -> dict[str, Any]:
    address = ipaddress.ip_address(source_ip)
    current = int(time.time()) if now is None else int(now)
    family = "ipv4" if address.version == 4 else "ipv6"
    key = _session_key(session_token)

    state = store.read("client-sources.json", {})
    if not isinstance(state, dict):
        state = {}
    sessions = state.setdefault("sessions", {})
    if not isinstance(sessions, dict):
        sessions = {}
        state["sessions"] = sessions

    for session_id, record in list(sessions.items()):
        if not isinstance(record, dict):
            sessions.pop(session_id, None)
            continue
        families = record.get("families")
        if not isinstance(families, dict):
            sessions.pop(session_id, None)
            continue
        for fam, item in list(families.items()):
            if not isinstance(item, dict) or int(item.get("expires_at", 0) or 0) <= current:
                families.pop(fam, None)
        if not families:
            sessions.pop(session_id, None)

    record = sessions.setdefault(key, {"families": {}})
    families = record.setdefault("families", {})
    families[family] = {
        "address": str(address),
        "observed_at": current,
        "expires_at": current + max(30, min(int(ttl), SOURCE_TTL)),
    }
    store.write("client-sources.json", state)
    return {"family": family, **families[family]}


def trusted_sources(
    store: JsonStore,
    session_token: str,
    *,
    now: int | None = None,
) -> dict[str, dict[str, Any]]:
    current = int(time.time()) if now is None else int(now)
    state = store.read("client-sources.json", {})
    sessions = state.get("sessions") if isinstance(state, dict) else None
    record = sessions.get(_session_key(session_token)) if isinstance(sessions, dict) else None
    families = record.get("families") if isinstance(record, dict) else None
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(families, dict):
        return result
    for family in ("ipv4", "ipv6"):
        item = families.get(family)
        if not isinstance(item, dict) or int(item.get("expires_at", 0) or 0) <= current:
            continue
        try:
            address = ipaddress.ip_address(str(item.get("address") or ""))
        except ValueError:
            continue
        if (family == "ipv4" and address.version != 4) or (family == "ipv6" and address.version != 6):
            continue
        result[family] = {
            "address": str(address),
            "observed_at": int(item.get("observed_at", 0) or 0),
            "expires_at": int(item.get("expires_at", 0) or 0),
        }
    return result


def source_for_family(store: JsonStore, session_token: str, family: str, *, now: int | None = None) -> str:
    if family not in {"ipv4", "ipv6"}:
        raise ValueError("invalid_family")
    item = trusted_sources(store, session_token, now=now).get(family)
    if not item:
        raise ValueError("client_source_not_observed")
    return str(item["address"])


def delete_sources(store: JsonStore, session_token: str) -> None:
    state = store.read("client-sources.json", {})
    sessions = state.get("sessions") if isinstance(state, dict) else None
    if not isinstance(sessions, dict):
        return
    sessions.pop(_session_key(session_token), None)
    state["sessions"] = sessions
    store.write("client-sources.json", state)
