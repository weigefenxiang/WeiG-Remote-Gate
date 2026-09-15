from __future__ import annotations

from typing import Any

from .gate import QUEUE_LOCK, _queue_for_write
from .store import JsonStore


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
