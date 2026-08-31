#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from app.client_sources import (
    OBSERVER_TOKEN_TTL,
    issue_observer_token,
    observer_hostnames,
    observer_url,
    redeem_observer_token,
)
from app.main import Handler as BaseHandler
from app.main import SETTINGS, STORE
from app.security import host_matches


CALLBACK_RE = re.compile(r"^__weigObserver_[A-Za-z0-9_]{8,96}$")


def _hostname(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if text.startswith("["):
        closing = text.find("]")
        return text[1:closing] if closing > 0 else ""
    return text.split(":", 1)[0].rstrip(".")


class Handler(BaseHandler):
    def _observer_hosts(self) -> dict[str, str]:
        return observer_hostnames(SETTINGS.public_hostname)

    def _send_headers(self, status: int, content_type: str, length: int | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        observers = " ".join(f"https://{host}" for host in self._observer_hosts().values())
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            f"script-src 'self' {observers}; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
        )

    def _host_ok(self) -> bool:
        if host_matches(SETTINGS, self.headers.get("Host")):
            return True
        if _hostname(self.headers.get("Host")) in set(self._observer_hosts().values()):
            return True
        self._json(421, {"error": "invalid_host"})
        return False

    def _observer_response(self, callback: str, ok: bool) -> None:
        payload = json.dumps({"ok": ok}, separators=(",", ":"))
        self._text(200, f"{callback}({payload});\n", "application/javascript; charset=utf-8")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        request_host = _hostname(self.headers.get("Host"))
        observer_hosts = self._observer_hosts()

        if request_host in set(observer_hosts.values()):
            if path != "/api/v1/client-source/observe":
                self._empty(404)
                return
            query = parse_qs(parsed.query)
            callback = (query.get("callback") or [""])[0]
            token = (query.get("token") or [""])[0]
            if not CALLBACK_RE.fullmatch(callback) or not token:
                self._empty(400)
                return
            source = self._trusted_client_ip()
            if not source:
                self._observer_response(callback, False)
                return
            try:
                redeem_observer_token(
                    STORE,
                    token,
                    source,
                    request_host,
                    SETTINGS.public_hostname,
                    SETTINGS.session_secret,
                )
            except ValueError:
                self._observer_response(callback, False)
                return
            self._observer_response(callback, True)
            return

        if path == "/api/v1/client-source/challenge":
            if not self._host_ok():
                return
            session = self._require_session()
            if not session:
                return
            family = (parse_qs(parsed.query).get("family") or [""])[0]
            if family not in {"ipv4", "ipv6"}:
                self._json(400, {"error": "invalid_family"})
                return
            token = issue_observer_token(session.token, family, SETTINGS.session_secret)
            self._json(
                200,
                {
                    "family": family,
                    "url": observer_url(SETTINGS.public_hostname, family, token),
                    "expires_in": OBSERVER_TOKEN_TTL,
                },
            )
            return

        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        request_host = _hostname(self.headers.get("Host"))
        if request_host in set(self._observer_hosts().values()):
            self._empty(404)
            return
        if path == "/api/v1/client-source/probe":
            if not self._host_ok():
                return
            self._json(410, {"error": "untrusted_source_probe_disabled"})
            return
        super().do_POST()


def run() -> None:
    server = ThreadingHTTPServer((SETTINGS.bind_host, SETTINGS.bind_port), Handler)
    observers = observer_hostnames(SETTINGS.public_hostname)
    print(
        f"WeiG-Remote-Gate listening on {SETTINGS.bind_host}:{SETTINGS.bind_port} "
        f"for {SETTINGS.public_hostname}; source observers: "
        f"{observers['ipv4']}, {observers['ipv6']}"
    )
    server.serve_forever()


if __name__ == "__main__":
    run()
