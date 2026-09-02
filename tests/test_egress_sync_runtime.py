import os
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EGRESS = ROOT / "openwrt/remote-gate-wireguard-egress.sh"


def fake_cmd(directory: Path, name: str, body: str = "exit 0\n") -> None:
    path = directory / name
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class EgressSyncRuntimeTests(unittest.TestCase):
    def run_fw4_sync(self, nft_mode: str):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        fake_bin = root / "bin"
        fake_bin.mkdir()
        runtime = root / "runtime"
        runtime.mkdir()
        state = runtime / "wireguard-egress.conf"
        ip_cleared = root / "ip-cleared"
        nft_cleared = root / "nft-cleared"
        expires = int(time.time()) + 600
        state.write_text(
            "\n".join(
                [
                    "ENABLED='1'",
                    "MODE='dual'",
                    "WG_INTERFACE='WG_HOME'",
                    "WG_DEVICE='wg0'",
                    "WAN_INTERFACE=''",
                    "WAN_DEVICE=''",
                    "WAN_INTERFACE4='WAN4'",
                    "WAN_DEVICE4='pppoe-WAN4'",
                    "WAN_INTERFACE6='WAN6'",
                    "WAN_DEVICE6='pppoe-WAN6'",
                    "WG_SUBNET4='10.7.0.0/24'",
                    "WG_SUBNET6='fd00:7::/64'",
                    "FIREWALL_BACKEND='fw4-nftables'",
                    "ROUTE_TABLE4='51820'",
                    "ROUTE_TABLE6='52020'",
                    "RULE_BASE4='80'",
                    "RULE_BASE6='80'",
                    f"EXPIRES_AT='{expires}'",
                    "TOKEN='fixture-token'",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        fake_cmd(fake_bin, "id", "[ \"${1:-}\" = -u ] && { echo 0; exit 0; }; exit 0\n")
        fake_cmd(
            fake_bin,
            "ubus",
            """case "${2:-}" in
    network.interface.WG_HOME) dev=wg0 ;;
    network.interface.WAN4) dev=pppoe-WAN4 ;;
    network.interface.WAN6) dev=pppoe-WAN6 ;;
    *) exit 1 ;;
esac
printf 'up=true\nl3_device=%s\n' "$dev"
""",
        )
        fake_cmd(
            fake_bin,
            "jsonfilter",
            """input="$(cat)"
case "$*" in
    *'@.up'*) printf '%s\n' "$input" | sed -n 's/^up=//p' ;;
    *'@.l3_device'*) printf '%s\n' "$input" | sed -n 's/^l3_device=//p' ;;
    *) exit 1 ;;
esac
""",
        )
        fake_cmd(
            fake_bin,
            "ip",
            """family="${1:-}"
shift || true
case "$family:$*" in
    '-4:rule del '*|'-6:rule del '*) exit 0 ;;
    '-4:route flush table '*|'-6:route flush table '*)
        : > "$REMOTE_GATE_IP_CLEARED"
        exit 0
        ;;
    '-4:route flush cache'|'-6:route flush cache') exit 0 ;;
esac
if [ -e "$REMOTE_GATE_IP_CLEARED" ]; then
    case "$family:$*" in
        '-4:rule show'|'-6:rule show'|'-4:route show table 51820'|'-6:route show table 52020') exit 0 ;;
    esac
fi
case "$family:$*" in
    '-4:route show default dev pppoe-WAN4') echo 'default via 198.51.100.1 dev pppoe-WAN4' ;;
    '-4:route show table 51820 default dev pppoe-WAN4') echo 'default via 198.51.100.1 dev pppoe-WAN4' ;;
    '-6:route show default dev pppoe-WAN6') echo 'default via 2001:db8::1 dev pppoe-WAN6' ;;
    '-6:route show table 52020 default dev pppoe-WAN6') echo 'default via 2001:db8::1 dev pppoe-WAN6' ;;
    '-4:rule show') echo '90: from 10.7.0.0/24 iif wg0 lookup 51820' ;;
    '-6:rule show') echo '90: from fd00:7::/64 iif wg0 lookup 52020' ;;
    '-4:route show dev wg0 scope link') echo '10.7.0.0/24 dev wg0 scope link' ;;
    '-6:addr show dev wg0') echo 'inet6 fd00:7::1/64 scope global' ;;
    '-6:route show dev wg0') echo 'fd00:7::/64 dev wg0' ;;
    *) exit 0 ;;
esac
""",
        )
        fake_cmd(
            fake_bin,
            "nft",
            """if [ "${1:-}" = delete ] && [ "${2:-}" = rule ]; then
    if [ "${REMOTE_GATE_NFT_MODE:-full}" != missing-v6-nat66-stuck ]; then
        : > "$REMOTE_GATE_NFT_CLEARED"
    fi
    exit 0
fi
if [ "${1:-}" = -a ] && [ "${2:-}" = list ] && [ "${3:-}" = chain ]; then
    [ ! -e "$REMOTE_GATE_NFT_CLEARED" ] || exit 0
    chain="${6:-}"
    if [ "$chain" = forward ]; then
        echo 'iifname "wg0" oifname "pppoe-WAN4" comment "WeiG Remote Gate WG egress v4 outbound" # handle 11'
        echo 'iifname "pppoe-WAN4" oifname "wg0" comment "WeiG Remote Gate WG egress v4 return" # handle 12'
        echo 'iifname "wg0" oifname "pppoe-WAN6" comment "WeiG Remote Gate WG egress v6 outbound" # handle 13'
        echo 'iifname "pppoe-WAN6" oifname "wg0" comment "WeiG Remote Gate WG egress v6 return" # handle 14'
    elif [ "$chain" = srcnat ]; then
        echo 'oifname "pppoe-WAN4" comment "WeiG Remote Gate WG egress v4 nat" # handle 21'
        case "${REMOTE_GATE_NFT_MODE:-full}" in
            missing-v6-nat66|missing-v6-nat66-stuck) ;;
            *) echo 'oifname "pppoe-WAN6" comment "WeiG Remote Gate WG egress v6 nat66" # handle 22' ;;
        esac
    fi
    exit 0
fi
exit 0
""",
        )
        fake_cmd(
            fake_bin,
            "uci",
            """if [ "${1:-}" = -q ] && [ "${2:-}" = get ] && [ "${3:-}" = network.WG_HOME.proto ]; then
    echo wireguard
    exit 0
fi
case "$*" in *' get '*) exit 1 ;; esac
exit 0
""",
        )
        fake_cmd(fake_bin, "logger")

        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:/usr/bin:/bin"
        env["REMOTE_GATE_RUNTIME_DIR"] = str(runtime)
        env["REMOTE_GATE_STATE_DIR"] = str(root / "persistent")
        env["REMOTE_GATE_NFT_MODE"] = nft_mode
        env["REMOTE_GATE_IP_CLEARED"] = str(ip_cleared)
        env["REMOTE_GATE_NFT_CLEARED"] = str(nft_cleared)
        proc = subprocess.run(
            ["/bin/sh", str(EGRESS), "sync"],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        return proc, state, runtime / "wireguard-egress-error.conf"

    def test_complete_fw4_dual_firewall_is_healthy(self):
        proc, state, error = self.run_fw4_sync("full")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(state.exists())
        self.assertFalse(error.exists())

    def test_missing_ipv6_nat66_is_not_treated_as_healthy_dual(self):
        proc, state, _error = self.run_fw4_sync("missing-v6-nat66")
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse(state.exists())

    def test_incomplete_cleanup_keeps_runtime_identity_for_retry(self):
        proc, state, _error = self.run_fw4_sync("missing-v6-nat66-stuck")
        self.assertNotEqual(proc.returncode, 0)
        self.assertTrue(state.exists())


if __name__ == "__main__":
    unittest.main()
