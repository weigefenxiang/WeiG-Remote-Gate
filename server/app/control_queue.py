from __future__ import annotations

from typing import Any

from .gate import QUEUE_LOCK, _queue_for_write
from .store import JsonStore


TERMINAL_CONTROL_STATES = {"failed", "cancelled", "expired"}


def queue_control_command(store: JsonStore, command: dict[str, Any]) -> dict[str, Any]:
    """Queue one non-Gate control command on the existing serialized Agent channel.

    Client-profile commands intentionally share the Gate command queue so OpenWrt never
    receives two state-changing instructions concurrently. The previous terminal command
    is retained because result validation may need to correlate an Agent response after ACK.
    """
    if not isinstance(command, dict) or command.get("state") != "pending" or not command.get("id"):
        raise ValueError("invalid_control_command")
    with QUEUE_LOCK:
        queue = _queue_for_write(store)
        store.write(
            "commands.json",
            {"pending": command, "next": [], "last": queue.get("last")},
        )
    return command


def terminal_control_error(store: JsonStore, command_id: object, action: str) -> str | None:
    """Return the terminal failure detail for one serialized control command, if any."""
    key = str(command_id or "").strip()
    if not key or not action:
        return None
    with QUEUE_LOCK:
        queue = store.read("commands.json", {})
        if not isinstance(queue, dict):
            return None
        for slot in ("pending", "last"):
            command = queue.get(slot)
            if not isinstance(command, dict):
                continue
            if command.get("id") != key or command.get("action") != action:
                continue
            state = str(command.get("state") or "")
            if state not in TERMINAL_CONTROL_STATES:
                return None
            detail = str(command.get("detail") or "").strip()
            return detail or f"{action}_{state}"
    return None
