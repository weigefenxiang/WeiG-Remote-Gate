import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "server/app/static/js/gate-controls.js"


class GateCloseUiContractTests(unittest.TestCase):
    def test_server_close_supersedes_local_activate_transaction(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn(
            "pending.action === 'close' && transaction.action === 'activate'",
            source,
        )
        self.assertIn(
            "last.action === 'close' && transaction.action === 'activate'",
            source,
        )
        self.assertIn("closeCreatedAt >= localStartedAt - 2", source)
        self.assertIn("transaction = {action:'close'", source)
        self.assertIn("serverOwned:true", source)


if __name__ == "__main__":
    unittest.main()
