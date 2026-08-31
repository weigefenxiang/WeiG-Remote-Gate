from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import ipaddress
import json
import secrets
import threading
import time
from typing import Any

from .store import JsonStore


SOURCE_TTL = 10 * 60
OBSERVER_TOKEN_TTL = 90
OBSERVER_REPLAY_TTL = 5 * 60
_OBSERVER_LOCK = threading.RLock()


def _session_key(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _valid_session_key(value: str) -> bool:
    return len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


def _state(store: JsonStore, current: int) -> tuple[dict[str, Any], dict[str, Any]]:
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
    return state, sessions


def _observe_verified(
    store: JsonStore,
    session_id: str,
    source_ip: str,
    *,
    source: str,
    now: int | None = None,
    ttl: int = SOURCE_TTL,
) -> dict[str, Any]:
    if not _valid_session_key(session_id):
        raise ValueError("invalid_session_key")
    address = ipaddress.ip_address(source_ip)
    current = int(time.time()) if now is None else int(now)
    family = "ipv4" if address.version == 4 else "ipv6"
    state, sessions = _state(store, current)

    record = sessions.setdefault(session_id, {"families": {}})
    families = record.setdefault("families", {})
    families[family] = {
        "address": str(address),
        "observed_at": current,
        "expires_at": current + max(30, min(int(ttl), SOURCE_TTL)),
        "source": source,
        "confidence": "verified",
    }
    store.write("client-sources.json", state)
    return {"family": family, **families[family]}


def observe_source(
    store: JsonStore,
    session_token: str,
    source_ip: str,
    *,
    now: int | None = None,
    ttl: int = SOURCE_TTL,
) -> dict[str, Any]:
    return _observe_verified(
        store,
        _session_key(session_token),
        source_ip,
        source="cloudflare",
        now=now,
        ttl=ttl,
    )


def observe_source_for_session_key(
    store: JsonStore,
    session_id: str,
    source_ip: str,
    *,
    now: int | None = None,
    ttl: int = SOURCE_TTL,
) -> dict[str, Any]:
    return _observe_verified(
        store,
        session_id,
        source_ip,
        source="cloudflare_observer",
        now=now,
        ttl=ttl,
    )


def observe_network_probe(*args, **kwargs) -> dict[str, Any]:
    """Legacy browser-reported source probes are intentionally disabled."""
    raise ValueError("untrusted_source_probe_disabled")


def observe_ipv4_probe(*args, **kwargs) -> dict[str, Any]:
    """Compatibility name retained so old imports fail closed."""
    raise ValueError("untrusted_source_probe_disabled")


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
            "source": str(item.get("source") or "cloudflare"),
            "confidence": str(item.get("confidence") or "verified"),
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


def observer_hostnames(public_hostname: str) -> dict[str, str]:
    base = str(public_hostname or "").strip().lower().rstrip(".")
    if not base or "/" in base or ":" in base:
        raise ValueError("invalid_public_hostname")
    return {"ipv4": f"v4.{base}", "ipv6": f"v6.{base}"}


def _b64_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def issue_observer_token(
    session_token: str,
    family: str,
    session_secret: bytes,
    *,
    now: int | None = None,
    ttl: int = OBSERVER_TOKEN_TTL,
) -> str:
    if family not in {"ipv4", "ipv6"}:
        raise ValueError("invalid_family")
    current = int(time.time()) if now is None else int(now)
    lifetime = max(30, min(int(ttl), OBSERVER_TOKEN_TTL))
    payload = {
        "sid": _session_key(session_token),
        "family": family,
        "exp": current + lifetime,
        "nonce": secrets.token_urlsafe(18),
    }
    body = _b64_encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(session_secret, b"source-observer:" + body.encode("ascii"), hashlib.sha256).digest()
    return body + "." + _b64_encode(signature)


def observer_url(public_hostname: str, family: str, token: str) -> str:
    host = observer_hostnames(public_hostname).get(family)
    if not host:
        raise ValueError("invalid_family")
    return f"https://{host}/api/v1/client-source/observe?token={token}"


def _decode_observer_token(token: str, session_secret: bytes) -> dict[str, Any]:
    try:
        body, supplied = token.split(".", 1)
        expected = hmac.new(session_secret, b"source-observer:" + body.encode("ascii"), hashlib.sha256).digest()
        actual = _b64_decode(supplied)
        if not hmac.compare_digest(actual, expected):
            raise ValueError("invalid_observer_token")
        payload = json.loads(_b64_decode(body).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error) as exc:
        raise ValueError("invalid_observer_token") from exc
    if not isinstance(payload, dict):
        raise ValueError("invalid_observer_token")
    return payload


def redeem_observer_token(
    store: JsonStore,
    token: str,
    source_ip: str,
    request_hostname: str,
    public_hostname: str,
    session_secret: bytes,
    *,
    now: int | None = None,
) -> dict[str, Any]:
    current = int(time.time()) if now is None else int(now)
    payload = _decode_observer_token(token, session_secret)
    session_id = str(payload.get("sid") or "")
    family = str(payload.get("family") or "")
    nonce = str(payload.get("nonce") or "")
    try:
        expires = int(payload.get("exp", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid_observer_token") from exc

    if not _valid_session_key(session_id) or family not in {"ipv4", "ipv6"} or len(nonce) < 16:
        raise ValueError("invalid_observer_token")
    if expires <= current:
        raise ValueError("observer_token_expired")

    expected_host = observer_hostnames(public_hostname)[family]
    actual_host = str(request_hostname or "").strip().lower().rstrip(".")
    if actual_host != expected_host:
        raise ValueError("observer_host_mismatch")

    address = ipaddress.ip_address(source_ip)
    expected_version = 4 if family == "ipv4" else 6
    if address.version != expected_version or not address.is_global:
        raise ValueError("observer_family_mismatch")

    token_id = hashlib.sha256(token.encode("ascii")).hexdigest()
    with _OBSERVER_LOCK:
        sessions = store.read("sessions.json", {})
        session_record = sessions.get(session_id) if isinstance(sessions, dict) else None
        if not isinstance(session_record, dict) or int(session_record.get("expires_at", 0) or 0) <= current:
            raise ValueError("observer_session_expired")

        replay = store.read("source-observer-replay.json", {})
        if not isinstance(replay, dict):
            replay = {}
        replay = {
            key: value
            for key, value in replay.items()
            if isinstance(value, int) and value > current
        }
        if token_id in replay:
            raise ValueError("observer_token_replayed")

        record = observe_source_for_session_key(store, session_id, str(address), now=current)
        replay[token_id] = min(expires + OBSERVER_REPLAY_TTL, current + OBSERVER_REPLAY_TTL)
        store.write("source-observer-replay.json", replay)
        return record
