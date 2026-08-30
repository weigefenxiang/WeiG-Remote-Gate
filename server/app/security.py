from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import secrets
import time
from dataclasses import dataclass
from http import cookies

from .config import Settings
from .store import JsonStore


COOKIE_NAME = "__Host-remotegate_session"
SESSION_SECONDS = 12 * 60 * 60
REMEMBER_SECONDS = 30 * 24 * 60 * 60


def safe_ip(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def client_ip(headers) -> str | None:
    return safe_ip(headers.get("CF-Connecting-IP"))


def is_private_wan_ipv4(value: str) -> bool:
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False
    if addr.version != 4:
        return False
    return (
        addr.is_private
        or addr in ipaddress.ip_network("100.64.0.0/10")
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
    )


def verify_password(settings: Settings, password: str) -> bool:
    expected = bytes.fromhex(settings.password_hash_hex)
    actual = hashlib.scrypt(
        password.encode("utf-8"),
        salt=bytes.fromhex(settings.salt_hex),
        n=settings.scrypt_n,
        r=settings.scrypt_r,
        p=settings.scrypt_p,
        dklen=settings.scrypt_dklen,
    )
    return hmac.compare_digest(actual, expected)


def new_token() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def csrf_for(settings: Settings, token: str) -> str:
    return hmac.new(
        settings.session_secret,
        b"csrf:" + token.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


@dataclass
class Session:
    token: str
    csrf: str
    expires_at: int


def create_session(settings: Settings, store: JsonStore, remember: bool) -> Session:
    token = new_token()
    now = int(time.time())
    ttl = REMEMBER_SECONDS if remember else SESSION_SECONDS
    expires = now + ttl
    sessions = store.read("sessions.json", {})
    if not isinstance(sessions, dict):
        sessions = {}
    sessions[token_hash(token)] = {"expires_at": expires, "created_at": now}
    sessions = {
        key: value
        for key, value in sessions.items()
        if isinstance(value, dict) and int(value.get("expires_at", 0)) > now
    }
    store.write("sessions.json", sessions)
    return Session(token=token, csrf=csrf_for(settings, token), expires_at=expires)


def parse_session(settings: Settings, store: JsonStore, cookie_header: str | None) -> Session | None:
    if not cookie_header:
        return None
    jar = cookies.SimpleCookie()
    try:
        jar.load(cookie_header)
    except cookies.CookieError:
        return None
    morsel = jar.get(COOKIE_NAME)
    if not morsel:
        return None
    token = morsel.value
    sessions = store.read("sessions.json", {})
    record = sessions.get(token_hash(token)) if isinstance(sessions, dict) else None
    now = int(time.time())
    if not isinstance(record, dict) or int(record.get("expires_at", 0)) <= now:
        return None
    return Session(token=token, csrf=csrf_for(settings, token), expires_at=int(record["expires_at"]))


def delete_session(store: JsonStore, token: str) -> None:
    sessions = store.read("sessions.json", {})
    if not isinstance(sessions, dict):
        return
    sessions.pop(token_hash(token), None)
    store.write("sessions.json", sessions)


def session_cookie(token: str, expires_at: int) -> str:
    jar = cookies.SimpleCookie()
    jar[COOKIE_NAME] = token
    morsel = jar[COOKIE_NAME]
    morsel["path"] = "/"
    morsel["secure"] = True
    morsel["httponly"] = True
    morsel["samesite"] = "Strict"
    morsel["max-age"] = str(max(0, expires_at - int(time.time())))
    return morsel.OutputString()


def clear_session_cookie() -> str:
    return f"{COOKIE_NAME}=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Strict"


def bearer_matches(settings: Settings, authorization: str | None) -> bool:
    if not authorization or not authorization.startswith("Bearer "):
        return False
    candidate = authorization[7:].strip()
    return hmac.compare_digest(candidate, settings.write_token)


def host_matches(settings: Settings, host_header: str | None) -> bool:
    if not host_header:
        return False
    host = host_header.strip().lower()
    if host.startswith("["):
        return host.startswith("[::1]")
    host = host.split(":", 1)[0].rstrip(".")
    return host in {settings.public_hostname, "127.0.0.1", "localhost"}
