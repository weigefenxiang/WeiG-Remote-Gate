from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    config_dir: Path
    state_dir: Path
    public_hostname: str
    bind_host: str
    bind_port: int
    write_token: str
    session_secret: bytes
    username: str
    salt_hex: str
    password_hash_hex: str
    scrypt_n: int
    scrypt_r: int
    scrypt_p: int
    scrypt_dklen: int


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def load_settings() -> Settings:
    config_dir = Path(os.environ.get("REMOTE_GATE_CONFIG_DIR", "/etc/remote-gate"))
    state_dir = Path(os.environ.get("REMOTE_GATE_STATE_DIR", "/var/lib/remote-gate"))

    config = _read_json(config_dir / "config.json")
    auth = _read_json(config_dir / "auth.json")
    secrets = _read_json(config_dir / "secrets.json")

    hostname = str(config["public_hostname"]).strip().lower().rstrip(".")
    bind_host = str(config.get("bind_host", "127.0.0.1"))
    bind_port = int(config.get("bind_port", 29444))
    write_token = str(secrets["write_token"])
    session_secret = bytes.fromhex(str(secrets["session_secret_hex"]))

    if bind_host not in {"127.0.0.1", "::1"}:
        raise RuntimeError("Refusing to bind WeiG-Remote-Gate to a non-loopback address")
    if len(write_token) < 32:
        raise RuntimeError("WRITE_TOKEN is too short")
    if len(session_secret) < 32:
        raise RuntimeError("SESSION_SECRET is too short")

    params = auth.get("scrypt", {})
    return Settings(
        config_dir=config_dir,
        state_dir=state_dir,
        public_hostname=hostname,
        bind_host=bind_host,
        bind_port=bind_port,
        write_token=write_token,
        session_secret=session_secret,
        username=str(auth["username"]),
        salt_hex=str(auth["salt_hex"]),
        password_hash_hex=str(auth["password_hash_hex"]),
        scrypt_n=int(params.get("n", 16384)),
        scrypt_r=int(params.get("r", 8)),
        scrypt_p=int(params.get("p", 1)),
        scrypt_dklen=int(params.get("dklen", 32)),
    )
