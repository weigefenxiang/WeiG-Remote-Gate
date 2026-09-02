import copy
import os
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from server.app.gate import ack_command
from server.app.store import JsonStore

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "openwrt/remote-gate-agent.sh"


def fake_cmd(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def agent_harness_source(
    config: Path,
    firewall: Path,
    egress: Path,
    services: Path,
    mapping: Path,
    state_dir: Path,
    tmp_base: Path,
) -> str:
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
    source = source.replace('TMP_BASE="/tmp/remote-gate-agent.$$"', f'TMP_BASE="{tmp_base}.$$"')
    return source.split('case "${1:-once}" in', 1)[0]


def basic_config(path: Path) -> None:
    path.write_text(
        "HOSTNAME='gate.example'\n"
        "WRITE_TOKEN='test-token'\n"
        "GATE_IPV6='disabled'\n"
        "MAPPED_ACCESS='disabled'\n",
        encoding="utf-8",
    )


def install_successor_jsonfilter(fake_bin: Path) -> None:
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
    '@.id') printf '%s\n' 'successor' ;;
    '@.action') printf '%s\n' 'activate' ;;
    '@.expires_at') printf '%s\n' '4102444800' ;;
    '@.source_ip') printf '%s\n' '198.51.100.7' ;;
    '@.source_confidence') printf '%s\n' 'verified' ;;
    '@.family') printf '%s\n' 'ipv4' ;;
    '@.scope') printf '%s\n' 'wg' ;;
    '@.access_method') printf '%s\n' 'direct' ;;
    '@.transport') printf '%s\n' 'udp' ;;
    '@.wan') printf '%s\n' 'WAN2' ;;
    '@.device') printf '%s\n' 'pppoe-WAN2' ;;
    '@.service_id') printf '%s\n' 'wg.WG_HOME' ;;
    '@.service_type') printf '%s\n' 'wireguard' ;;
    '@.wireguard') printf '%s\n' 'WG_HOME' ;;
    '@.ingress_port') printf '%s\n' '41194' ;;
    '@.service_port') printf '%s\n' '41194' ;;
    '@.external_address') printf '%s\n' '203.0.113.10' ;;
    '@.external_port') printf '%s\n' '41194' ;;
    '@.egress_mode') printf '%s\n' 'ipv4' ;;
    '@.batch_index') printf '%s\n' '1' ;;
    '@.batch_count') printf '%s\n' '2' ;;
    '@.predecessor_command_id') printf '%s\n' 'predecessor' ;;
    '@.ttl') printf '%s\n' '300' ;;
esac
''',
    )


class ServerAckDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = JsonStore(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_success_ack_advances_batch_with_predecessor_proof_and_is_idempotent(self):
        now = int(time.time())
        first = {
            "id": "first",
            "action": "activate",
            "family": "ipv4",
            "batch_id": "batch",
            "batch_index": 0,
            "batch_count": 2,
            "state": "pending",
            "created_at": now,
            "expires_at": now + 60,
        }
        second = {
            "id": "second",
            "action": "activate",
            "family": "ipv6",
            "batch_id": "batch",
            "batch_index": 1,
            "batch_count": 2,
            "state": "pending",
            "created_at": now,
            "expires_at": now + 60,
        }
        self.store.write("commands.json", {"pending": first, "next": [second], "last": None})

        self.assertTrue(ack_command(self.store, "first", True, "v4-active"))
        queue = self.store.read("commands.json", {})
        self.assertEqual(queue["last"]["id"], "first")
        self.assertEqual(queue["last"]["state"], "done")
        self.assertEqual(queue["pending"]["id"], "second")
        self.assertEqual(queue["pending"]["predecessor_command_id"], "first")
        self.assertEqual(queue["next"], [])

        snapshot = copy.deepcopy(queue)
        activity = copy.deepcopy(self.store.read("activity.json", []))
        self.assertTrue(ack_command(self.store, "first", True, "duplicate-response-retry"))
        self.assertEqual(self.store.read("commands.json", {}), snapshot)
        self.assertEqual(self.store.read("activity.json", []), activity)
        self.assertFalse(ack_command(self.store, "first", False, "mismatched-result"))
        self.assertEqual(self.store.read("commands.json", {}), snapshot)

    def test_duplicate_failed_followup_ack_does_not_replace_rollback_close(self):
        now = int(time.time())
        second = {
            "schema": 3,
            "id": "second",
            "action": "activate",
            "family": "ipv6",
            "source_ip": "2001:4860:4860::8888",
            "batch_id": "batch",
            "batch_index": 1,
            "batch_count": 2,
            "ttl": 300,
            "state": "pending",
            "created_at": now,
            "expires_at": now + 60,
        }
        self.store.write("commands.json", {"pending": second, "next": [], "last": None})

        self.assertTrue(ack_command(self.store, "second", False, "failed-v6"))
        queue = self.store.read("commands.json", {})
        self.assertEqual(queue["last"]["id"], "second")
        self.assertEqual(queue["last"]["state"], "failed")
        self.assertEqual(queue["pending"]["action"], "close")
        self.assertEqual(queue["pending"]["rollback_for_batch"], "batch")

        snapshot = copy.deepcopy(queue)
        activity = copy.deepcopy(self.store.read("activity.json", []))
        self.assertTrue(ack_command(self.store, "second", False, "duplicate-response-retry"))
        self.assertEqual(self.store.read("commands.json", {}), snapshot)
        self.assertEqual(self.store.read("activity.json", []), activity)
        self.assertFalse(ack_command(self.store, "second", True, "mismatched-result"))
        self.assertEqual(self.store.read("commands.json", {}), snapshot)


class AgentAckDeliveryRuntimeTests(unittest.TestCase):
    def test_confirmed_batch_predecessor_keeps_runtime_and_executes_successor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            state_dir = root / "state"
            runtime_dir = root / "runtime"
            runtime_dir.mkdir()
            config = root / "remote-gate.conf"
            tmp_base = root / "remote-gate-agent"
            mapping = root / "mapping-missing"
            firewall_log = root / "firewall.log"
            egress_log = root / "egress.log"
            ack_log = root / "ack.log"
            order_log = root / "order.log"

            basic_config(config)
            (runtime_dir / "agent-command-result").write_text(
                "predecessor\ntrue\nweb-authorization-active-pending-egress\n",
                encoding="utf-8",
            )
            firewall = fake_cmd(
                fake_bin,
                "firewall",
                r'''printf '%s\n' "$*" >> "$REMOTE_GATE_FIREWALL_LOG"
case "${1:-}" in
    status-json)
        printf '%s' '{"backend":"test","ready":true,"ipv6_capable":false,"active":true,"family":"ipv4","scope":"wg","expires_in":300,"source_ip":"198.51.100.7","device":"pppoe-WAN2","wg_port":41194,"ingress_port":41194,"families":{"ipv4":{"active":true,"family":"ipv4","scope":"wg","expires_in":300,"source_ip":"198.51.100.7","device":"pppoe-WAN2","wg_port":41194,"ingress_port":41194},"ipv6":{"active":false,"family":"ipv6","scope":"","expires_in":0,"source_ip":"","device":"","wg_port":0,"ingress_port":0}}}'
        ;;
esac
exit 0
''',
            )
            egress = fake_cmd(
                fake_bin,
                "egress",
                r'''printf '%s\n' "$*" >> "$REMOTE_GATE_EGRESS_LOG"
case "${1:-}" in
    status-json)
        printf '%s' '{"active":false,"state":"inactive","mode":"","wan":"","device":"","wan_v4":"","device_v4":"","wan_v6":"","device_v6":"","wg":"","ipv4_subnet":"","ipv6_subnet":"","detail":"","expires_in":0}'
        ;;
esac
exit 0
''',
            )
            services = fake_cmd(
                fake_bin,
                "services",
                r'''case "${1:-}" in
    validate) exit 0 ;;
    ports) printf '%s\n' '41194'; exit 0 ;;
    *) exit 0 ;;
esac
''',
            )
            install_successor_jsonfilter(fake_bin)

            source = agent_harness_source(
                config, firewall, egress, services, mapping, state_dir, tmp_base
            )
            source += r'''

sync_firewall_policy() { return 0; }
wireguard_json() { printf '[]'; }
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
        POST:/api/v1/agent/status)
            printf '%s\n' 'status' >> "$REMOTE_GATE_ORDER_LOG"
            CONTROL_CODE=204
            return 0
            ;;
        POST:/api/v1/agent/ack)
            printf '%s\n' "$payload" >> "$REMOTE_GATE_ACK_LOG"
            printf '%s\n' 'ack' >> "$REMOTE_GATE_ORDER_LOG"
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
            env["REMOTE_GATE_ACK_LOG"] = str(ack_log)
            env["REMOTE_GATE_ORDER_LOG"] = str(order_log)
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
            self.assertIn(
                "activate 198.51.100.7 ipv4 wg pppoe-WAN2 41194 300 web_verified",
                firewall_calls,
            )
            self.assertNotIn("clear", firewall_calls)
            self.assertNotIn("disable", egress_calls)
            self.assertEqual(len(ack_payloads), 1)
            self.assertIn('"id":"successor"', ack_payloads[0])
            self.assertIn('"ok":true', ack_payloads[0])
            self.assertEqual(order_log.read_text(encoding="utf-8").splitlines(), ["status", "ack"])
            self.assertFalse((runtime_dir / "agent-command-result").exists())

    def test_success_result_waits_for_status_and_replays_after_empty_pull(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_dir = root / "state"
            runtime_dir = root / "runtime"
            config = root / "remote-gate.conf"
            tmp_base = root / "remote-gate-agent"
            event_log = root / "events.log"
            basic_config(config)

            source = AGENT.read_text(encoding="utf-8")
            source = source.replace('CONFIG_FILE="/etc/remote-gate.conf"', f'CONFIG_FILE="{config}"')
            source = source.replace('STATE_DIR="/etc/remote-gate-state"', f'STATE_DIR="{state_dir}"')
            source = source.replace('TMP_BASE="/tmp/remote-gate-agent.$$"', f'TMP_BASE="{tmp_base}.$$"')
            source = source.split('case "${1:-once}" in', 1)[0]
            source += r'''

status_ready=0
post_status() {
    printf 'status:%s\n' "$status_ready" >> "$REMOTE_GATE_EVENT_LOG"
    [ "$status_ready" -eq 1 ]
}
send_ack() {
    printf 'ack:%s:%s:%s\n' "$1" "$2" "$3" >> "$REMOTE_GATE_EVENT_LOG"
    return 0
}
control_request() {
    method="$1"; path="$2"; output="$3"
    case "$method:$path" in
        GET:/api/v1/agent/pull)
            printf '%s\n' 'get' >> "$REMOTE_GATE_EVENT_LOG"
            : > "$output"
            CONTROL_CODE=204
            return 0
            ;;
        *) return 1 ;;
    esac
}

finish_activation_command single true active
if [ -f "$COMMAND_RESULT_FILE" ]; then printf '%s\n' 'journal:present' >> "$REMOTE_GATE_EVENT_LOG"; fi
status_ready=1
pull_once all
if [ -f "$COMMAND_RESULT_FILE" ]; then printf '%s\n' 'journal:present-after' >> "$REMOTE_GATE_EVENT_LOG"; else printf '%s\n' 'journal:absent' >> "$REMOTE_GATE_EVENT_LOG"; fi
'''
            harness = root / "agent-harness.sh"
            harness.write_text(source, encoding="utf-8")

            env = os.environ.copy()
            env["REMOTE_GATE_RUNTIME_DIR"] = str(runtime_dir)
            env["REMOTE_GATE_EVENT_LOG"] = str(event_log)
            proc = subprocess.run(
                ["/bin/sh", str(harness)],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(
                event_log.read_text(encoding="utf-8").splitlines(),
                [
                    "status:0",
                    "journal:present",
                    "get",
                    "status:1",
                    "ack:single:true:active",
                    "journal:absent",
                ],
            )
            self.assertFalse((runtime_dir / "agent-command-result").exists())


if __name__ == "__main__":
    unittest.main()
