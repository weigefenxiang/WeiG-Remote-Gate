import os
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOTPLUG = ROOT / "openwrt" / "remote-gate-hotplug.sh"
INIT = ROOT / "openwrt" / "remote-gate-agent.init"


def fake_ip(directory: Path) -> None:
    path = directory / "ip"
    path.write_text(
        r'''#!/bin/sh
printf '%s\n' "$*" >> "$IP_LOG"

case "$*" in
    "link show $TEST_DEVICE") exit 0 ;;
esac

flag=""
case "${1:-}" in
    -4|-6) flag="$1"; shift ;;
esac

case "$*" in
    "rule show")
        printf '0: from all lookup local\n'
        if [ "$EXISTING_TABLE" = "1" ]; then
            printf '1003: from all iif %s lookup %s\n' "$TEST_DEVICE" "$TEST_TABLE"
            printf '2003: from all fwmark 0x300/0x3f00 lookup %s\n' "$TEST_TABLE"
        fi
        if [ -f "$RULE_STATE" ]; then
            printf '900: from all iif lo to %s lookup %s\n' "$TEST_TARGET" "$ACTIVE_TABLE"
        fi
        printf '32766: from all lookup main\n'
        ;;
    "route get $TEST_SOURCE table $TEST_TABLE")
        printf '%s via %s dev %s src %s\n' "$TEST_SOURCE" "$TEST_GATEWAY" "$TEST_DEVICE" "$TEST_LOCAL_SOURCE"
        ;;
    "route get $TEST_SOURCE iif lo")
        if [ -f "$RULE_STATE" ]; then
            printf '%s via %s dev %s src %s\n' "$TEST_SOURCE" "$TEST_GATEWAY" "$TEST_DEVICE" "$TEST_LOCAL_SOURCE"
        else
            printf '%s via %s dev %s src %s\n' "$TEST_SOURCE" "$BASE_GATEWAY" "$BASE_DEVICE" "$BASE_SOURCE"
        fi
        ;;
    "route get $TEST_SOURCE")
        printf '%s via %s dev %s src %s\n' "$TEST_SOURCE" "$BASE_GATEWAY" "$BASE_DEVICE" "$BASE_SOURCE"
        ;;
    "route get $TEST_SOURCE oif $TEST_DEVICE")
        printf '%s via %s dev %s src %s\n' "$TEST_SOURCE" "$TEST_GATEWAY" "$TEST_DEVICE" "$TEST_LOCAL_SOURCE"
        ;;
    route\ show\ table\ *)
        ;;
    rule\ add\ priority\ *)
        printf '%s\n' "$*" > "$RULE_STATE"
        ;;
    rule\ del\ priority\ *)
        rm -f "$RULE_STATE"
        ;;
    route\ add\ table\ *)
        printf '%s\n' "$*" > "$ROUTE_STATE"
        ;;
    route\ del\ table\ *)
        rm -f "$ROUTE_STATE"
        ;;
    *)
        printf 'unexpected ip call: %s %s\n' "$flag" "$*" >&2
        exit 1
        ;;
esac
''',
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class ReturnRoutingTests(unittest.TestCase):
    def run_sync(
        self,
        *,
        family="ipv4",
        source="112.96.150.36",
        device="pppoe-WAN3",
        port=51877,
        table="3",
        existing_table=True,
        base_device="pppoe-WAN",
        gateway="198.51.100.1",
        local_source="198.51.100.2",
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bindir = root / "bin"
            bindir.mkdir()
            fake_ip(bindir)
            log = root / "ip.log"
            auth_dir = root / "firewall"
            auth_dir.mkdir()
            expires = int(time.time()) + 300
            (auth_dir / "authorization").write_text(
                f"{source}\n{device}\n{port}\n{expires}\n{family}\nwg_ping\n",
                encoding="utf-8",
            )
            flag = "-4" if family == "ipv4" else "-6"
            target = f"{source}/32" if family == "ipv4" else f"{source}/128"
            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{bindir}:/usr/bin:/bin",
                    "REMOTE_GATE_STATE_DIR": str(root),
                    "IP_LOG": str(log),
                    "RULE_STATE": str(root / "rule.state"),
                    "ROUTE_STATE": str(root / "route.state"),
                    "TEST_FLAG": flag,
                    "TEST_SOURCE": source,
                    "TEST_TARGET": target,
                    "TEST_DEVICE": device,
                    "TEST_TABLE": table,
                    "TEST_GATEWAY": gateway,
                    "TEST_LOCAL_SOURCE": local_source,
                    "BASE_DEVICE": base_device,
                    "BASE_GATEWAY": "172.20.0.1",
                    "BASE_SOURCE": "172.20.111.32",
                    "EXISTING_TABLE": "1" if existing_table else "0",
                    "ACTIVE_TABLE": table if existing_table else "51880",
                }
            )
            proc = subprocess.run(
                ["/bin/sh", str(HOTPLUG), "return-route-sync"],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            calls = log.read_text(encoding="utf-8") if log.exists() else ""
            state = (root / "return-route").read_text(encoding="utf-8") if (root / "return-route").exists() else ""
            return proc, calls, state

    def test_wan3_and_custom_wireguard_port_use_discovered_policy_table(self):
        proc, calls, state = self.run_sync()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("-4 route get 112.96.150.36 table 3", calls)
        self.assertIn("-4 rule add priority 900 iif lo to 112.96.150.36/32 lookup 3", calls)
        self.assertIn("\npppoe-WAN3\n51877\n3\n900\nexisting\n", "\n" + state)
        self.assertNotIn("51820", calls)

    def test_wan1_is_not_special_cased(self):
        proc, calls, state = self.run_sync(
            device="pppoe-WAN",
            port=51999,
            table="1",
            gateway="172.20.0.1",
            local_source="172.20.111.32",
            base_device="pppoe-WAN",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("-4 rule add priority 900 iif lo to 112.96.150.36/32 lookup 1", calls)
        self.assertIn("\npppoe-WAN\n51999\n1\n", "\n" + state)

    def test_ipv6_uses_host_local_128_rule(self):
        proc, calls, state = self.run_sync(
            family="ipv6",
            source="2001:db8:100::55",
            device="pppoe-WAN3",
            port=52001,
            table="7",
            gateway="2001:db8:3::1",
            local_source="2001:db8:3::2",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("-6 rule add priority 900 iif lo to 2001:db8:100::55/128 lookup 7", calls)
        self.assertIn("\nipv6\n", "\n" + state)
        self.assertIn("\n52001\n7\n", "\n" + state)

    def test_fallback_owned_table_is_destination_only_and_local_only(self):
        proc, calls, state = self.run_sync(existing_table=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(
            "-4 route add table 51880 112.96.150.36/32 via 198.51.100.1 dev pppoe-WAN3 src 198.51.100.2",
            calls,
        )
        self.assertIn("-4 rule add priority 900 iif lo to 112.96.150.36/32 lookup 51880", calls)
        self.assertIn("\nowned\n", "\n" + state)

    def test_expired_authorization_removes_managed_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bindir = root / "bin"
            bindir.mkdir()
            fake_ip(bindir)
            log = root / "ip.log"
            auth_dir = root / "firewall"
            auth_dir.mkdir()
            (auth_dir / "authorization").write_text(
                f"112.96.150.36\npppoe-WAN3\n51877\n{int(time.time()) - 1}\nipv4\nwg_ping\n",
                encoding="utf-8",
            )
            (root / "return-route").write_text(
                "ipv4\n112.96.150.36\npppoe-WAN3\n51877\n3\n900\nexisting\n"
                "ipv4|112.96.150.36|pppoe-WAN3|51877|3|existing\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{bindir}:/usr/bin:/bin",
                    "REMOTE_GATE_STATE_DIR": str(root),
                    "IP_LOG": str(log),
                    "RULE_STATE": str(root / "rule.state"),
                    "ROUTE_STATE": str(root / "route.state"),
                    "TEST_SOURCE": "112.96.150.36",
                    "TEST_TARGET": "112.96.150.36/32",
                    "TEST_DEVICE": "pppoe-WAN3",
                    "TEST_TABLE": "3",
                    "TEST_GATEWAY": "198.51.100.1",
                    "TEST_LOCAL_SOURCE": "198.51.100.2",
                    "BASE_DEVICE": "pppoe-WAN",
                    "BASE_GATEWAY": "172.20.0.1",
                    "BASE_SOURCE": "172.20.111.32",
                    "EXISTING_TABLE": "1",
                    "ACTIVE_TABLE": "3",
                }
            )
            proc = subprocess.run(
                ["/bin/sh", str(HOTPLUG), "return-route-sync"],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            calls = log.read_text(encoding="utf-8")
            self.assertIn("-4 rule del priority 900 iif lo to 112.96.150.36/32 lookup 3", calls)
            self.assertFalse((root / "return-route").exists())

    def test_contract_is_local_only_dynamic_and_lifecycle_managed(self):
        source = HOTPLUG.read_text(encoding="utf-8")
        init = INIT.read_text(encoding="utf-8")
        self.assertIn('iif lo to "$target" lookup "$table"', source)
        self.assertIn('candidate_tables "$flag" "$wanted"', source)
        self.assertIn('port="$(sed -n \'3p\' "$AUTH_FILE")"', source)
        self.assertIn("return-route-loop", init)
        self.assertIn("return-route-clear", init)
        self.assertNotIn("FORWARD", source)
        self.assertNotIn("pppoe-WAN2", source)
        self.assertNotIn("51820", source)


if __name__ == "__main__":
    unittest.main()
