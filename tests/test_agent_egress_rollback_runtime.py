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


class AgentEgressRollbackRuntimeTests(unittest.TestCase):
    def test_single_family_egress_failure_revokes_gate_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            state_dir = root / "state"
            config = root / "remote-gate.conf"
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
            fake_cmd(
                fake_bin,
                "jsonfilter",
                """expr=''
while [ "$#" -gt 0 ]; do
    case "$1" in
        -e) shift; expr="${1:-}" ;;
    esac
    shift || true
done
case "$expr" in
    '@.id') printf '%s\n' 'cmd-1' ;;
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
    '@.egress_wan') printf '%s\n' 'WAN2' ;;
    '@.egress_wan_ipv4') printf '%s\n' 'WAN2' ;;
    '@.egress_mode') printf '%s\n' 'ipv4' ;;
    '@.batch_index') printf '%s\n' '0' ;;
    '@.batch_count') printf '%s\n' '1' ;;
    '@.ttl') printf '%s\n' '300' ;;
esac
""",
            )

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
                f'MAPPING="{root / "mapping-missing"}"',
            )
            source = source.replace('STATE_DIR="/etc/remote-gate-state"', f'STATE_DIR="{state_dir}"')
            source = source.replace(
                'TMP_BASE="/tmp/remote-gate-agent.$$"',
                f'TMP_BASE="{root / "remote-gate-agent"}.$$"',
            )
            source = source.split('case "${1:-once}" in', 1)[0]
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


if __name__ == "__main__":
    unittest.main()
