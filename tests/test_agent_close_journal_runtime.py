import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "openwrt/remote-gate-agent.sh"


def fake_cmd(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def harness_source(config: Path, firewall: Path, egress: Path, state_dir: Path, tmp_base: Path) -> str:
    source = AGENT.read_text(encoding="utf-8")
    source = source.replace('CONFIG_FILE="/etc/remote-gate.conf"', f'CONFIG_FILE="{config}"')
    source = source.replace(
        'FIREWALL="/usr/lib/remote-gate/remote-gate-firewall.sh"',
        f'FIREWALL="{firewall}"',
    )
    source = source.replace(
        'EGRESS="/usr/lib/remote-gate/remote-gate-wireguard-egress.sh"',
        f'EGRESS="{egress}"',
    )
    source = source.replace('STATE_DIR="/etc/remote-gate-state"', f'STATE_DIR="{state_dir}"')
    source = source.replace('TMP_BASE="/tmp/remote-gate-agent.$$"', f'TMP_BASE="{tmp_base}.$$"')
    return source.split('case "${1:-once}" in', 1)[0]


def install_close_jsonfilter(fake_bin: Path) -> None:
    fake_cmd(
        fake_bin,
        "jsonfilter",
        r'''expr=''
while [ "$#" -gt 0 ]; do
    case "$1" in
        -e) shift; expr="${1:-}" ;;
    esac
    shift || true
done
case "$expr" in
    '@.id') printf '%s\n' 'close-1' ;;
    '@.action') printf '%s\n' 'close' ;;
    '@.expires_at') printf '%s\n' '4102444800' ;;
esac
''',
    )


class AgentCloseJournalRuntimeTests(unittest.TestCase):
    def test_close_keeps_activation_journal_until_cleanup_converges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            state_dir = root / "state"
            runtime_dir = root / "runtime"
            runtime_dir.mkdir()
            config = root / "remote-gate.conf"
            tmp_base = root / "remote-gate-agent"
            firewall_log = root / "firewall.log"
            firewall_count = root / "firewall.count"
            egress_log = root / "egress.log"
            ack_log = root / "ack.log"
            journal_log = root / "journal.log"

            config.write_text(
                "HOSTNAME='gate.example'\n"
                "WRITE_TOKEN='test-token'\n"
                "GATE_IPV6='disabled'\n"
                "MAPPED_ACCESS='disabled'\n",
                encoding="utf-8",
            )
            journal = runtime_dir / "agent-command-result"
            journal.write_text(
                "old-activate\ntrue\nweb-authorization-active\n",
                encoding="utf-8",
            )

            firewall = fake_cmd(
                fake_bin,
                "firewall",
                r'''printf '%s\n' "$*" >> "$REMOTE_GATE_FIREWALL_LOG"
if [ "${1:-}" = "clear" ]; then
    count="$(cat "$REMOTE_GATE_FIREWALL_COUNT" 2>/dev/null || echo 0)"
    count=$((count + 1))
    printf '%s\n' "$count" > "$REMOTE_GATE_FIREWALL_COUNT"
    [ "$count" -gt 1 ] || exit 1
fi
exit 0
''',
            )
            egress = fake_cmd(
                fake_bin,
                "egress",
                r'''printf '%s\n' "$*" >> "$REMOTE_GATE_EGRESS_LOG"
exit 0
''',
            )
            install_close_jsonfilter(fake_bin)

            source = harness_source(config, firewall, egress, state_dir, tmp_base)
            source += r'''

control_request() {
    method="$1"; path="$2"; output="$3"; payload="${4:-}"
    case "$method:$path" in
        GET:/api/v1/agent/pull)
            : > "$output"
            CONTROL_CODE=200
            CONTROL_FAMILY=ipv4
            CONTROL_DEVICE=pppoe-WAN2
            return 0
            ;;
        POST:/api/v1/agent/ack)
            printf '%s\n' "$payload" >> "$REMOTE_GATE_ACK_LOG"
            CONTROL_CODE=204
            return 0
            ;;
        *)
            CONTROL_CODE=204
            return 0
            ;;
    esac
}

pull_once all
if [ -f "$COMMAND_RESULT_FILE" ]; then printf 'present\n'; else printf 'absent\n'; fi >> "$REMOTE_GATE_JOURNAL_LOG"
pull_once all
if [ -f "$COMMAND_RESULT_FILE" ]; then printf 'present\n'; else printf 'absent\n'; fi >> "$REMOTE_GATE_JOURNAL_LOG"
'''
            harness = root / "agent-harness.sh"
            harness.write_text(source, encoding="utf-8")

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:/usr/bin:/bin"
            env["REMOTE_GATE_RUNTIME_DIR"] = str(runtime_dir)
            env["REMOTE_GATE_FIREWALL_LOG"] = str(firewall_log)
            env["REMOTE_GATE_FIREWALL_COUNT"] = str(firewall_count)
            env["REMOTE_GATE_EGRESS_LOG"] = str(egress_log)
            env["REMOTE_GATE_ACK_LOG"] = str(ack_log)
            env["REMOTE_GATE_JOURNAL_LOG"] = str(journal_log)
            proc = subprocess.run(
                ["/bin/sh", str(harness)],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(journal_log.read_text(encoding="utf-8").splitlines(), ["present", "absent"])
            self.assertFalse(journal.exists())

            firewall_calls = firewall_log.read_text(encoding="utf-8").splitlines()
            egress_calls = egress_log.read_text(encoding="utf-8").splitlines()
            ack_payloads = ack_log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(firewall_calls, ["clear", "clear"])
            self.assertEqual(egress_calls, ["disable", "disable"])
            self.assertEqual(len(ack_payloads), 2)
            self.assertIn('"ok":false', ack_payloads[0])
            self.assertIn('"detail":"gate-close-failed"', ack_payloads[0])
            self.assertIn('"ok":true', ack_payloads[1])
            self.assertIn('"detail":"all-authorizations-and-egress-cleared"', ack_payloads[1])

    def test_close_does_not_clear_journal_before_expiry_validation(self):
        source = AGENT.read_text(encoding="utf-8")
        pre_expiry = source.split('expires_at="$(jsonfilter', 1)[0]
        self.assertNotIn("else\n        clear_activation_result", pre_expiry)
        close_body = source.split("        close)", 1)[1].split("        *)", 1)[0]
        self.assertIn('if [ "$close_ok" = true ]; then', close_body)
        self.assertIn("if clear_activation_result; then", close_body)
        self.assertLess(close_body.index('if [ "$close_ok" = true ]; then'), close_body.index("if clear_activation_result; then"))


if __name__ == "__main__":
    unittest.main()
