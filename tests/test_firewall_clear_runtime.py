import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIREWALL = ROOT / "openwrt/remote-gate-firewall.sh"


def fake_cmd(directory: Path, name: str, body: str = "exit 0\n") -> None:
    path = directory / name
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def seed_state(root: Path, backend: str) -> Path:
    state_base = root / "state"
    state = state_base / "firewall"
    auth_v4 = state / "authorization-ipv4.d"
    auth_v6 = state / "authorization-ipv6.d"
    auth_v4.mkdir(parents=True)
    auth_v6.mkdir(parents=True)
    (state / "backend").write_text(backend + "\n", encoding="utf-8")
    (state / "protected-devices-v4").write_text("pppoe-WAN\n", encoding="utf-8")
    (state / "protected-devices-v6").write_text("", encoding="utf-8")
    (state / "protected-ports").write_text("41194\n", encoding="utf-8")
    (state / "mapped-ingress-v4").write_text("", encoding="utf-8")
    (state / "mapped-control-v4").write_text("", encoding="utf-8")
    auth_file = auth_v4 / "198.51.100.7"
    auth_file.write_text(
        "198.51.100.7\npppoe-WAN\n41194\n4102444800\nipv4\nwg\nweb_observed\n",
        encoding="utf-8",
    )
    return state_base


class FirewallClearRuntimeTests(unittest.TestCase):
    def run_clear(self, root: Path, state_base: Path):
        env = os.environ.copy()
        env["PATH"] = f"{root / 'bin'}:/usr/bin:/bin"
        env["REMOTE_GATE_STATE_DIR"] = str(state_base)
        env["REMOTE_GATE_LIB_DIR"] = str(ROOT / "openwrt")
        env["REMOTE_GATE_CLEAR_FAIL_MARKER"] = str(root / "fail-once")
        env["REMOTE_GATE_CLEAR_LOG"] = str(root / "clear.log")
        return subprocess.run(
            ["/bin/sh", str(FIREWALL), "clear", "all"],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

    def test_fw4_clear_failure_is_retryable_after_state_identity_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            state_base = seed_state(root, "fw4-nftables")
            marker = root / "fail-once"
            marker.write_text("1\n", encoding="utf-8")
            fake_cmd(fake_bin, "fw4")
            fake_cmd(
                fake_bin,
                "nft",
                """printf '%s\n' "$*" >> "$REMOTE_GATE_CLEAR_LOG"
if [ "${1:-}" = "list" ] && [ "${2:-}" = "set" ]; then
    exit 0
fi
if [ "${1:-}" = "flush" ] && [ "${2:-}" = "set" ]; then
    if [ "${5:-}" = "weig_remote_gate_auth_ipv4" ] && [ -f "$REMOTE_GATE_CLEAR_FAIL_MARKER" ]; then
        rm -f "$REMOTE_GATE_CLEAR_FAIL_MARKER"
        exit 1
    fi
    exit 0
fi
if [ "${1:-}" = "-f" ] && [ "${2:-}" = "-" ]; then
    cat >/dev/null
    exit 0
fi
exit 0
""",
            )

            first = self.run_clear(root, state_base)
            self.assertNotEqual(first.returncode, 0, first.stderr)
            self.assertFalse((state_base / "firewall/authorization-ipv4.d/198.51.100.7").exists())

            second = self.run_clear(root, state_base)
            self.assertEqual(second.returncode, 0, second.stderr)
            log = (root / "clear.log").read_text(encoding="utf-8")
            self.assertGreaterEqual(log.count("flush set inet fw4 weig_remote_gate_auth_ipv4"), 3)
            self.assertIn("flush set inet fw4 weig_remote_gate_auth_ifname_v4", log)
            self.assertIn("flush set inet fw4 weig_remote_gate_auth_ping_ifname_v4", log)
            self.assertIn("flush set inet fw4 weig_remote_gate_auth_udp_port_v4", log)

    def test_fw3_clear_failure_is_retryable_after_state_identity_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            state_base = seed_state(root, "fw3-iptables")
            marker = root / "fail-once"
            marker.write_text("1\n", encoding="utf-8")
            fake_cmd(fake_bin, "fw3")
            fake_cmd(fake_bin, "ip6tables", "exit 1\n")
            fake_cmd(
                fake_bin,
                "iptables",
                """if [ "${1:-}" = "-C" ]; then exit 1; fi
exit 0
""",
            )
            fake_cmd(
                fake_bin,
                "ipset",
                """printf '%s\n' "$*" >> "$REMOTE_GATE_CLEAR_LOG"
if [ "${1:-}" = "list" ] && [ "${2:-}" = "-name" ]; then
    printf '%s\n' weig_remote_gate_auth_v4 weig_remote_gate_verify_v4
    exit 0
fi
if [ "${1:-}" = "list" ]; then exit 0; fi
if [ "${1:-}" = "flush" ]; then
    if [ "${2:-}" = "weig_remote_gate_auth_v4" ] && [ -f "$REMOTE_GATE_CLEAR_FAIL_MARKER" ]; then
        rm -f "$REMOTE_GATE_CLEAR_FAIL_MARKER"
        exit 1
    fi
    exit 0
fi
if [ "${1:-}" = "help" ]; then exit 1; fi
exit 0
""",
            )

            first = self.run_clear(root, state_base)
            self.assertNotEqual(first.returncode, 0, first.stderr)
            self.assertFalse((state_base / "firewall/authorization-ipv4.d/198.51.100.7").exists())

            second = self.run_clear(root, state_base)
            self.assertEqual(second.returncode, 0, second.stderr)
            log = (root / "clear.log").read_text(encoding="utf-8")
            self.assertGreaterEqual(log.count("flush weig_remote_gate_auth_v4"), 3)


if __name__ == "__main__":
    unittest.main()
