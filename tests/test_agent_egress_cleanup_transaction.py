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


def agent_harness_source(config, firewall, egress, services, mapping, state_dir, tmp_base):
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
    source = source.replace(
        'SERVICES="/usr/lib/remote-gate/remote-gate-service-registry.sh"',
        f'SERVICES="{services}"',
    )
    source = source.replace(
        'MAPPING="/usr/lib/remote-gate/remote-gate-mapping.sh"',
        f'MAPPING="{mapping}"',
    )
    source = source.replace('STATE_DIR="/etc/remote-gate-state"', f'STATE_DIR="{state_dir}"')
    source = source.replace(
        'TMP_BASE="/tmp/remote-gate-agent.$$"',
        f'TMP_BASE="{tmp_base}.$$"',
    )
    return source.split('case "${1:-once}" in', 1)[0]


def basic_config(path: Path) -> None:
    path.write_text(
        "HOSTNAME='gate.example'\n"
        "WRITE_TOKEN='test-token'\n"
        "GATE_IPV6='disabled'\n"
        "MAPPED_ACCESS='disabled'\n",
        encoding="utf-8",
    )


def install_jsonfilter(fake_bin: Path, command_id: str, egress_mode: str) -> None:
    egress_wan = "WAN2" if egress_mode == "ipv4" else ""
    fake_cmd(
        fake_bin,
        "jsonfilter",
        f"""expr=''
while [ "$#" -gt 0 ]; do
    case "$1" in
        -e) shift; expr="${{1:-}}" ;;
    esac
    shift || true
done
case "$expr" in
    '@.id') printf '%s\\n' '{command_id}' ;;
    '@.action') printf '%s\\n' 'activate' ;;
    '@.expires_at') printf '%s\\n' '4102444800' ;;
    '@.source_ip') printf '%s\\n' '198.51.100.7' ;;
    '@.source_confidence') printf '%s\\n' 'verified' ;;
    '@.family') printf '%s\\n' 'ipv4' ;;
    '@.scope') printf '%s\\n' 'wg' ;;
    '@.access_method') printf '%s\\n' 'direct' ;;
    '@.transport') printf '%s\\n' 'udp' ;;
    '@.wan') printf '%s\\n' 'WAN2' ;;
    '@.device') printf '%s\\n' 'pppoe-WAN2' ;;
    '@.service_id') printf '%s\\n' 'wg.WG_HOME' ;;
    '@.service_type') printf '%s\\n' 'wireguard' ;;
    '@.wireguard') printf '%s\\n' 'WG_HOME' ;;
    '@.ingress_port') printf '%s\\n' '41194' ;;
    '@.service_port') printf '%s\\n' '41194' ;;
    '@.egress_wan') printf '%s\\n' '{egress_wan}' ;;
    '@.egress_wan_ipv4') printf '%s\\n' '{egress_wan}' ;;
    '@.egress_wan_ipv6') printf '%s\\n' '' ;;
    '@.egress_mode') printf '%s\\n' '{egress_mode}' ;;
    '@.batch_index') printf '%s\\n' '0' ;;
    '@.batch_count') printf '%s\\n' '1' ;;
    '@.ttl') printf '%s\\n' '300' ;;
esac
""",
    )


class AgentEgressCleanupTransactionTests(unittest.TestCase):
    def run_activate(self, *, command_id: str, egress_mode: str, fail_first_disable: bool):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        fake_bin = root / "bin"
        fake_bin.mkdir()
        state_dir = root / "state"
        config = root / "remote-gate.conf"
        mapping = root / "mapping-missing"
        tmp_base = root / "remote-gate-agent"
        runtime_dir = root / "runtime"
        firewall_log = root / "firewall.log"
        egress_log = root / "egress.log"
        egress_count = root / "egress.count"
        ack_log = root / "ack.log"

        basic_config(config)
        firewall = fake_cmd(
            fake_bin,
            "firewall",
            """printf '%s\\n' "$*" >> "$REMOTE_GATE_FIREWALL_LOG"
exit 0
""",
        )
        egress = fake_cmd(
            fake_bin,
            "egress",
            """printf '%s' "${1:-}" >> "$REMOTE_GATE_EGRESS_LOG"
if [ "${1:-}" = disable ]; then
    count="$(cat "$REMOTE_GATE_EGRESS_COUNT" 2>/dev/null || echo 0)"
    count=$((count + 1))
    printf '%s\\n' "$count" > "$REMOTE_GATE_EGRESS_COUNT"
    journal="$REMOTE_GATE_RUNTIME_DIR/agent-command-result"
    if [ -r "$journal" ] &&
       [ "$(sed -n '1p' "$journal")" = "$REMOTE_GATE_COMMAND_ID" ] &&
       [ "$(sed -n '2p' "$journal")" = pending ]; then
        printf ' journal=pending\\n' >> "$REMOTE_GATE_EGRESS_LOG"
    else
        printf ' journal=missing\\n' >> "$REMOTE_GATE_EGRESS_LOG"
        printf 'ERROR: activation-journal-missing-before-egress-cleanup\\n' >&2
        exit 2
    fi
    if [ "${REMOTE_GATE_FAIL_FIRST_DISABLE:-0}" = 1 ] && [ "$count" -eq 1 ]; then
        printf 'ERROR: simulated-existing-egress-disable-failure\\n' >&2
        exit 1
    fi
    exit 0
fi
shift || true
printf ' %s\\n' "$*" >> "$REMOTE_GATE_EGRESS_LOG"
exit 0
""",
        )
        services = fake_cmd(fake_bin, "services", "exit 0\n")
        fake_cmd(fake_bin, "logger", "exit 0\n")
        install_jsonfilter(fake_bin, command_id, egress_mode)

        source = agent_harness_source(
            config, firewall, egress, services, mapping, state_dir, tmp_base
        )
        source += r'''

sync_firewall_policy() { return 0; }
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
'''
        harness = root / "agent-harness.sh"
        harness.write_text(source, encoding="utf-8")

        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:/usr/bin:/bin"
        env["REMOTE_GATE_RUNTIME_DIR"] = str(runtime_dir)
        env["REMOTE_GATE_FIREWALL_LOG"] = str(firewall_log)
        env["REMOTE_GATE_EGRESS_LOG"] = str(egress_log)
        env["REMOTE_GATE_EGRESS_COUNT"] = str(egress_count)
        env["REMOTE_GATE_ACK_LOG"] = str(ack_log)
        env["REMOTE_GATE_COMMAND_ID"] = command_id
        env["REMOTE_GATE_FAIL_FIRST_DISABLE"] = "1" if fail_first_disable else "0"

        proc = subprocess.run(
            ["/bin/sh", str(harness)],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        firewall_calls = (
            firewall_log.read_text(encoding="utf-8").splitlines()
            if firewall_log.exists()
            else []
        )
        egress_calls = (
            egress_log.read_text(encoding="utf-8").splitlines()
            if egress_log.exists()
            else []
        )
        ack_payloads = (
            ack_log.read_text(encoding="utf-8").splitlines()
            if ack_log.exists()
            else []
        )
        return proc, runtime_dir, firewall_calls, egress_calls, ack_payloads

    def test_existing_egress_cleanup_is_journaled_before_side_effect(self):
        proc, runtime_dir, firewall_calls, egress_calls, ack_payloads = self.run_activate(
            command_id="cmd-preclean-fail",
            egress_mode="ipv4",
            fail_first_disable=True,
        )

        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(
            egress_calls,
            ["disable journal=pending", "disable journal=pending"],
        )
        self.assertEqual(firewall_calls, ["clear"])
        self.assertEqual(len(ack_payloads), 1)
        self.assertIn('"id":"cmd-preclean-fail"', ack_payloads[0])
        self.assertIn('"ok":false', ack_payloads[0])
        self.assertIn(
            '"detail":"simulated-existing-egress-disable-failure"',
            ack_payloads[0],
        )
        self.assertFalse((runtime_dir / "agent-command-result").exists())

    def test_none_exit_cleans_old_egress_once_before_firewall_activate(self):
        proc, runtime_dir, firewall_calls, egress_calls, ack_payloads = self.run_activate(
            command_id="cmd-none-exit",
            egress_mode="",
            fail_first_disable=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(egress_calls, ["disable journal=pending"])
        self.assertEqual(
            firewall_calls,
            ["activate 198.51.100.7 ipv4 wg pppoe-WAN2 41194 300 web_verified"],
        )
        self.assertEqual(len(ack_payloads), 1)
        self.assertIn('"id":"cmd-none-exit"', ack_payloads[0])
        self.assertIn('"ok":true', ack_payloads[0])
        self.assertNotIn("egress-active", ack_payloads[0])
        self.assertFalse((runtime_dir / "agent-command-result").exists())


if __name__ == "__main__":
    unittest.main()
