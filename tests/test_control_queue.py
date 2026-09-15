from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from app.control_queue import queue_control_command, terminal_control_error  # noqa: E402
from app.gate import ack_command  # noqa: E402
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

    def test_terminal_control_error_reports_failed_profile_create_ack(self):
        with tempfile.TemporaryDirectory() as td:
            store = JsonStore(Path(td))
            command = {
                "id": "b" * 32,
                "action": "profile_create",
                "state": "pending",
                "expires_at": 9999999999,
            }
            queue_control_command(store, command)
            self.assertTrue(ack_command(store, command["id"], False, "profile-ipv4-pool-exhausted"))
            self.assertEqual(
                terminal_control_error(store, command["id"], "profile_create"),
                "profile-ipv4-pool-exhausted",
            )

    def test_terminal_control_error_ignores_pending_done_and_other_actions(self):
        with tempfile.TemporaryDirectory() as td:
            store = JsonStore(Path(td))
            command = {
                "id": "c" * 32,
                "action": "profile_create",
                "state": "pending",
                "expires_at": 9999999999,
            }
            queue_control_command(store, command)
            self.assertIsNone(terminal_control_error(store, command["id"], "profile_create"))
            self.assertTrue(ack_command(store, command["id"], True, "client-profile-created"))
            self.assertIsNone(terminal_control_error(store, command["id"], "profile_create"))
            self.assertIsNone(terminal_control_error(store, command["id"], "profile_revoke"))


if __name__ == "__main__":
    unittest.main()
