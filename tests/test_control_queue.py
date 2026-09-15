from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from app.control_queue import queue_control_command  # noqa: E402
from app.store import JsonStore  # noqa: E402


class ControlQueueTests(unittest.TestCase):
    def test_non_gate_command_preserves_previous_terminal_last(self):
        with tempfile.TemporaryDirectory() as td:
            store = JsonStore(Path(td))
            previous = {"id": "a" * 32, "action": "profile_create", "state": "done"}
            store.write("commands.json", {"pending": None, "next": [], "last": previous})
            command = {"id": "b" * 32, "action": "profile_revoke", "state": "pending", "expires_at": 9999999999}
            queue_control_command(store, command)
            queue = store.read("commands.json", {})
            self.assertEqual(queue["pending"]["id"], command["id"])
            self.assertEqual(queue["last"], previous)


if __name__ == "__main__":
    unittest.main()
