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

    def test_carrier_ipv4_probe_is_session_and_csrf_bound(self):
        source = MAIN.read_text(encoding="utf-8")
        block = source.split('if path == "/api/v1/client-source/probe":', 1)[1].split(
            'if path == "/api/v1/gate/activate":', 1
        )[0]
        self.assertIn("self._require_session()", block)
        self.assertIn("self._require_csrf(session)", block)
        self.assertIn("observe_ipv4_probe", block)
        self.assertIn("_safe_ipv4", block)

    def test_csp_allows_only_the_ipv4_probe_script_origin(self):
        source = MAIN.read_text(encoding="utf-8")
        self.assertIn("script-src 'self' https://api.ipify.org", source)
        self.assertIn("connect-src 'self'", source)


if __name__ == "__main__":
    unittest.main()
