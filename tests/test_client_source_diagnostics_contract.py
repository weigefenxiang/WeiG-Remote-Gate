import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT_SOURCES = ROOT / "server/app/static/js/client-sources.js"


class ClientSourceDiagnosticsContractTests(unittest.TestCase):
    def test_candidate_diagnostics_match_current_source_authority_model(self):
        source = CLIENT_SOURCES.read_text(encoding="utf-8")
        self.assertIn("short-lived session source evidence", source)
        self.assertNotIn("waiting for WireGuard verification", source)
        self.assertNotIn("Carrier candidate remains fresh'", source)


if __name__ == "__main__":
    unittest.main()
