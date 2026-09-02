import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AgentAckAuthorityTests(unittest.TestCase):
    def test_agent_ack_requires_json_boolean_before_queue_owner_is_called(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "config"
            state_dir = root / "state"
            config_dir.mkdir()
            state_dir.mkdir()
            (config_dir / "config.json").write_text(
                json.dumps({
                    "public_hostname": "gate.example",
                    "bind_host": "127.0.0.1",
                    "bind_port": 29444,
                }),
                encoding="utf-8",
            )
            (config_dir / "auth.json").write_text(
                json.dumps({
                    "username": "test",
                    "salt_hex": "00",
                    "password_hash_hex": "00",
                    "scrypt": {"n": 16384, "r": 8, "p": 1, "dklen": 32},
                }),
                encoding="utf-8",
            )
            (config_dir / "secrets.json").write_text(
                json.dumps({
                    "write_token": "t" * 32,
                    "session_secret_hex": "00" * 32,
                }),
                encoding="utf-8",
            )

            script = r'''
from server.app import main


def exercise(payload):
    calls = []
    responses = []
    main.ack_command = lambda *args: calls.append(args) or True

    class Dummy:
        path = "/api/v1/agent/ack"
        def _host_ok(self): return True
        def _require_agent(self): return True
        def _read_json(self): return payload
        def _json(self, status, value): responses.append((status, value))
        def _empty(self, status): responses.append((status, None))

    main.Handler.do_POST(Dummy())
    return calls, responses

calls, responses = exercise({"id":"close-1","ok":"false","detail":"cleanup failed"})
assert calls == [], calls
assert responses == [(400, {"error":"invalid_ack"})], responses

calls, responses = exercise({"id":"close-1","ok":False,"detail":"cleanup failed"})
assert len(calls) == 1, calls
assert calls[0][1] == "close-1", calls
assert calls[0][2] is False, calls
assert calls[0][3] == "cleanup failed", calls
assert responses == [(204, None)], responses
'''
            env = os.environ.copy()
            env["REMOTE_GATE_CONFIG_DIR"] = str(config_dir)
            env["REMOTE_GATE_STATE_DIR"] = str(state_dir)
            env["PYTHONPATH"] = str(ROOT)
            proc = subprocess.run(
                [sys.executable, "-c", script],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)


if __name__ == "__main__":
    unittest.main()
