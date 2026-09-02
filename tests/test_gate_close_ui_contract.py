import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "server/app/static/js/gate-controls.js"


class GateCloseUiContractTests(unittest.TestCase):
    def test_server_close_supersedes_local_activate_by_exact_identity(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn("function closeSupersedesTransaction(command)", source)
        self.assertIn("command.preempted_batch_id === transaction.batchId", source)
        self.assertIn("command.rollback_for_batch === transaction.batchId", source)
        self.assertIn("command.preempted_command_id === transaction.commandId", source)
        self.assertIn("if (pending && closeSupersedesTransaction(pending))", source)
        self.assertIn("if (!pending && last && closeSupersedesTransaction(last))", source)
        self.assertIn("function adoptCloseTransaction(command)", source)
        self.assertNotIn("closeCreatedAt >= localStartedAt - 2", source)
        self.assertIn("serverOwned:true", source)


if __name__ == "__main__":
    unittest.main()
