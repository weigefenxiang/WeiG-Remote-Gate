import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "server/app/main.py"


class ServerContractTests(unittest.TestCase):
    def test_gate_routes_return_conflict_for_pending_command(self):
        source = MAIN.read_text(encoding="utf-8")
        activate = source.split('if path == "/api/v1/gate/activate":', 1)[1].split(
            'if path == "/api/v1/gate/close":', 1
        )[0]
        close = source.split('if path == "/api/v1/gate/close":', 1)[1].split(
            'if path == "/api/v1/update":', 1
        )[0]
        expected = 'status = 409 if str(exc) == "command_pending" else 400'
        self.assertIn(expected, activate)
        self.assertIn("except GateError as exc:", close)
        self.assertIn(expected, close)


if __name__ == "__main__":
    unittest.main()
