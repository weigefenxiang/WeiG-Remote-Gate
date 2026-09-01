import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "server/app/static/js/gate-controls.js"


class GateErrorFreshnessTests(unittest.TestCase):
    def test_historical_failed_command_does_not_render_forever(self):
        source = GATE.read_text(encoding="utf-8")
        self.assertIn("function recentTerminalFailure(last)", source)
        self.assertIn("last.acked_at || last.expires_at || last.created_at", source)
        self.assertIn("return age <= 120", source)
        self.assertIn("else if (recentTerminalFailure(last))", source)
        self.assertNotIn("else if (last?.state === 'failed' || last?.state === 'expired')", source)


if __name__ == "__main__":
    unittest.main()
