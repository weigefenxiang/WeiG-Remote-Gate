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


def install_jsonfilter(fake_bin: Path, command_id: str) -> None:
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
    '@.egress_wan') printf '%s\\n' 'WAN2' ;;
    '@.egress_wan_ipv4') printf '%s\\n' 'WAN2' ;;
    '@.egress_mode') printf '%s\\n' 'ipv4' ;;
    '@.batch_index') printf '%s\\n' '0' ;;
    '@.batch_count') printf '%s\\n' '1' ;;
    '@.ttl') printf '%s\\n' '300' ;;
esac
""",
    )


class AgentEgressRollbackRuntimeTests(unittest.TestCase):
    def test_single_family_egress_failure_revokes_gate_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            state_dir = root / "state"
            config = root / "remote-gate.conf"
            mapping = root / "mapping-missing"
            tmp_base = root / "remote-gate-agent"
            firewall_log = root / "firewall.log"
            egress_log = root / "egress.log"
            ack_log = root / "ack.log"

            config.write_text(
                "HOSTNAME='gate.example'\n"
                "WRITE_TOKEN='test-token'\n"
                "GATE_IPV6='disabled'\n"
                "MAPPED_ACCESS='disabled'\n",
                encoding="utf-8",
            )

            firewall = fake_cmd(
                fake_bin,
                "firewall",
                """printf '%s\n' "$*" >> "$REMOTE_GATE_FIREWALL_LOG"
exit 0
""",
            )
            egress = fake_cmd(
                fake_bin,
                "egress",
                """printf '%s\n' "$*" >> "$REMOTE_GATE_EGRESS_LOG"
case "${1:-}" in
    enable|enable-split)
        printf 'ERROR: simulated-egress-failure\n' >&2
        exit 1
        ;;
    *) exit 0 ;;
esac
""",
            )
            services = fake_cmd(fake_bin, "services", "exit 0\n")
            install_jsonfilter(fake_bin, "cmd-1")

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
            env["REMOTE_GATE_FIREWALL_LOG"] = str(firewall_log)
            env["REMOTE_GATE_EGRESS_LOG"] = str(egress_log)
            env["REMOTE_GATE_ACK_LOG"] = str(ack_log)
            env["REMOTE_GATE_RUNTIME_DIR"] = str(root / "runtime")
            proc = subprocess.run(
                ["/bin/sh", str(harness)],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            firewall_calls = firewall_log.read_text(encoding="utf-8").splitlines()
            egress_calls = egress_log.read_text(encoding="utf-8").splitlines()
            ack = ack_log.read_text(encoding="utf-8")

            activate = "activate 198.51.100.7 ipv4 wg pppoe-WAN2 41194 300 web_verified"
            self.assertIn(activate, firewall_calls)
            self.assertIn("clear", firewall_calls)
            self.assertLess(firewall_calls.index(activate), firewall_calls.index("clear"))

            self.assertEqual(egress_calls[0], "disable")
            self.assertIn("enable WG_HOME WAN2 300 ipv4", egress_calls)
            self.assertEqual(egress_calls[-1], "disable")
            self.assertEqual(egress_calls.count("disable"), 2)

            self.assertIn('"id":"cmd-1"', ack)
            self.assertIn('"ok":false', ack)
            self.assertIn('"detail":"simulated-egress-failure"', ack)
            self.assertNotIn('"ok":true', ack)

    def test_ack_retry_replays_result_without_reexecuting_activate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            state_dir = root / "state"
            config = root / "remote-gate.conf"
            mapping = root / "mapping-missing"
            tmp_base = root / "remote-gate-agent"
            runtime_dir = root / "runtime"
            firewall_log = root / "firewall.log"
            egress_log = root / "egress.log"
            ack_log = root / "ack.log"
            ack_count = root / "ack.count"

            config.write_text(
                "HOSTNAME='gate.example'\n"
                "WRITE_TOKEN='test-token'\n"
                "GATE_IPV6='disabled'\n"
                "MAPPED_ACCESS='disabled'\n",
                encoding="utf-8",
            )
            firewall = fake_cmd(
                fake_bin,
                "firewall",
                """printf '%s\n' "$*" >> "$REMOTE_GATE_FIREWALL_LOG"
exit 0
""",
            )
            egress = fake_cmd(
                fake_bin,
                "egress",
                """printf '%s\n' "$*" >> "$REMOTE_GATE_EGRESS_LOG"
exit 0
""",
            )
            services = fake_cmd(fake_bin, "services", "exit 0\n")
            install_jsonfilter(fake_bin, "cmd-replay")

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
            count="$(cat "$REMOTE_GATE_ACK_COUNT" 2>/dev/null || echo 0)"
            count=$((count + 1))
            printf '%s\n' "$count" > "$REMOTE_GATE_ACK_COUNT"
            if [ "$count" -eq 1 ]; then
                CONTROL_CODE=503
            else
                CONTROL_CODE=204
            fi
            return 0
            ;;
        *)
            CONTROL_CODE=204
            return 0
            ;;
    esac
}

pull_once all
pull_once all
'''
            harness = root / "agent-harness.sh"
            harness.write_text(source, encoding="utf-8")

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:/usr/bin:/bin"
            env["REMOTE_GATE_FIREWALL_LOG"] = str(firewall_log)
            env["REMOTE_GATE_EGRESS_LOG"] = str(egress_log)
            env["REMOTE_GATE_ACK_LOG"] = str(ack_log)
            env["REMOTE_GATE_ACK_COUNT"] = str(ack_count)
            env["REMOTE_GATE_RUNTIME_DIR"] = str(runtime_dir)
            proc = subprocess.run(
                ["/bin/sh", str(harness)],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            firewall_calls = firewall_log.read_text(encoding="utf-8").splitlines()
            egress_calls = egress_log.read_text(encoding="utf-8").splitlines()
            ack_payloads = ack_log.read_text(encoding="utf-8").splitlines()
            activate = "activate 198.51.100.7 ipv4 wg pppoe-WAN2 41194 300 web_verified"

            self.assertEqual(firewall_calls.count(activate), 1)
            self.assertEqual(egress_calls.count("enable WG_HOME WAN2 300 ipv4"), 1)
            self.assertEqual(len(ack_payloads), 2)
            self.assertEqual(ack_payloads[0], ack_payloads[1])
            self.assertIn('"ok":true', ack_payloads[0])
            self.assertFalse((runtime_dir / "agent-command-result").exists())

    def test_stale_pending_journal_rolls_back_before_new_activate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            state_dir = root / "state"
            config = root / "remote-gate.conf"
            mapping = root / "mapping-missing"
            tmp_base = root / "remote-gate-agent"
            runtime_dir = root / "runtime"
            firewall_log = root / "firewall.log"
            egress_log = root / "egress.log"
            ack_log = root / "ack.log"

            runtime_dir.mkdir()
            (runtime_dir / "agent-command-result").write_text(
                "old-cmd\npending\nactivation-in-progress\n", encoding="utf-8"
            )
            config.write_text(
                "HOSTNAME='gate.example'\n"
                "WRITE_TOKEN='test-token'\n"
                "GATE_IPV6='disabled'\n"
                "MAPPED_ACCESS='disabled'\n",
                encoding="utf-8",
            )
            firewall = fake_cmd(
                fake_bin,
                "firewall",
                """printf '%s\n' "$*" >> "$REMOTE_GATE_FIREWALL_LOG"
exit 0
""",
            )
            egress = fake_cmd(
                fake_bin,
                "egress",
                """printf '%s\n' "$*" >> "$REMOTE_GATE_EGRESS_LOG"
exit 0
""",
            )
            services = fake_cmd(fake_bin, "services", "exit 0\n")
            install_jsonfilter(fake_bin, "new-cmd")

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
            env["REMOTE_GATE_FIREWALL_LOG"] = str(firewall_log)
            env["REMOTE_GATE_EGRESS_LOG"] = str(egress_log)
            env["REMOTE_GATE_ACK_LOG"] = str(ack_log)
            env["REMOTE_GATE_RUNTIME_DIR"] = str(runtime_dir)
            proc = subprocess.run(
                ["/bin/sh", str(harness)],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            firewall_calls = firewall_log.read_text(encoding="utf-8").splitlines()
            egress_calls = egress_log.read_text(encoding="utf-8").splitlines()
            activate = "activate 198.51.100.7 ipv4 wg pppoe-WAN2 41194 300 web_verified"

            self.assertIn("clear", firewall_calls)
            self.assertIn(activate, firewall_calls)
            self.assertLess(firewall_calls.index("clear"), firewall_calls.index(activate))
            self.assertGreaterEqual(egress_calls.count("disable"), 2)
            self.assertIn('"id":"new-cmd"', ack_log.read_text(encoding="utf-8"))
            self.assertFalse((runtime_dir / "agent-command-result").exists())


if __name__ == "__main__":
    unittest.main()
