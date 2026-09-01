#!/bin/sh
set -eu
umask 077

RAW_BASE="${REMOTE_GATE_RAW_BASE:-https://raw.githubusercontent.com/weigefenxiang/WeiG-Remote-Gate/main}"
LIB_DIR="/usr/lib/remote-gate"
STATE_DIR="/etc/remote-gate-state"
CONFIG_FILE="/etc/remote-gate.conf"
INIT_FILE="/etc/init.d/remote-gate-agent"
HOTPLUG_FILE="/etc/hotplug.d/iface/95-remote-gate"
PLATFORM="$LIB_DIR/remote-gate-platform.sh"
CRON_LINE="*/5 * * * * /usr/lib/remote-gate/remote-gate-report.sh"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || fail "Run this installer as root."

# These are core runtime capabilities, not release-number gates. OpenWrt,
# LEDE, ImmortalWrt and compatible derivatives are accepted when they provide
# the required OpenWrt-family runtime interfaces.
for cmd in curl ubus jsonfilter awk sed grep sort uci ip; do
    command -v "$cmd" >/dev/null 2>&1 || fail "Missing core dependency: $cmd"
done
[ -r /etc/rc.common ] || fail "Missing OpenWrt rc.common service framework."

printf '\nWeiG Remote Gate OpenWrt-family installer\n\n'
printf 'Public hostname (example: remote.example.com): '
IFS= read -r HOSTNAME
HOSTNAME="${HOSTNAME#http://}"
HOSTNAME="${HOSTNAME#https://}"
HOSTNAME="${HOSTNAME%%/*}"
[ -n "$HOSTNAME" ] || fail "Hostname is required."

if command -v stty >/dev/null 2>&1; then
    printf 'WRITE_TOKEN from the VPS installer: '
    stty -echo
    trap 'stty echo 2>/dev/null || true' EXIT INT TERM
    IFS= read -r WRITE_TOKEN
    stty echo
    trap - EXIT INT TERM
    printf '\n'
else
    printf 'WRITE_TOKEN from the VPS installer (input will be visible on this minimal system): '
    IFS= read -r WRITE_TOKEN
fi
[ "${#WRITE_TOKEN}" -ge 32 ] || fail "WRITE_TOKEN is too short."

mkdir -p "$LIB_DIR" "$STATE_DIR" "$(dirname "$HOTPLUG_FILE")"
chmod 0755 "$LIB_DIR"
chmod 0700 "$STATE_DIR"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd -P)"
fetch_file() {
    rel="$1"; out="$2"
    if [ -f "$SCRIPT_DIR/$rel" ]; then
        cp "$SCRIPT_DIR/$rel" "$out"
    else
        curl -fsSL "$RAW_BASE/openwrt/$rel" -o "$out"
    fi
}

fetch_file "remote-gate-platform.sh" "$PLATFORM"
fetch_file "remote-gate-report.sh" "$LIB_DIR/remote-gate-report.sh"
fetch_file "remote-gate-agent.sh" "$LIB_DIR/remote-gate-agent.sh"
fetch_file "remote-gate-egress-probe.sh" "$LIB_DIR/remote-gate-egress-probe.sh"
fetch_file "remote-gate-wireguard-egress.sh" "$LIB_DIR/remote-gate-wireguard-egress.sh"
fetch_file "remote-gate-service-registry.sh" "$LIB_DIR/remote-gate-service-registry.sh"
fetch_file "remote-gate-mapping.sh" "$LIB_DIR/remote-gate-mapping.sh"
fetch_file "remote-gate-mapper-install.sh" "$LIB_DIR/remote-gate-mapper-install.sh"
fetch_file "remote-gate-firewall.sh" "$LIB_DIR/remote-gate-firewall.sh"
fetch_file "remote-gate-firewall-backends.sh" "$LIB_DIR/remote-gate-firewall-backends.sh"
fetch_file "remote-gate-wireguard-verify.sh" "$LIB_DIR/remote-gate-wireguard-verify.sh"
fetch_file "remote-gate-firewall-include.sh" "$LIB_DIR/remote-gate-firewall-include.sh"
fetch_file "remote-gate-audit.sh" "$LIB_DIR/remote-gate-audit.sh"
fetch_file "uninstall.sh" "$LIB_DIR/uninstall.sh"
fetch_file "update.sh" "$LIB_DIR/update.sh"
fetch_file "remote-gate-agent.init" "$INIT_FILE"
fetch_file "remote-gate-hotplug.sh" "$HOTPLUG_FILE"
chmod 0755 "$LIB_DIR"/*.sh "$INIT_FILE" "$HOTPLUG_FILE"

for file in "$LIB_DIR"/*.sh "$INIT_FILE" "$HOTPLUG_FILE"; do
    sh -n "$file" || fail "Shell syntax check failed: $file"
done

"$PLATFORM" core-capable || fail "Required OpenWrt-family core runtime capabilities are unavailable."
INIT_SYSTEM="$("$PLATFORM" init 2>/dev/null || printf unknown)"
case "$INIT_SYSTEM" in
    procd|rc.common) ;;
    *) fail "Unsupported OpenWrt-family service framework: $INIT_SYSTEM" ;;
esac
DIST="$("$PLATFORM" distribution 2>/dev/null || printf unknown)"
RELEASE="$("$PLATFORM" release 2>/dev/null || printf unknown)"
PKG_MANAGER="$("$PLATFORM" package-manager 2>/dev/null || printf none)"
PKG_ARCH="$("$PLATFORM" package-arch 2>/dev/null || true)"
KERNEL_ARCH="$("$PLATFORM" kernel-arch 2>/dev/null || printf unknown)"
LIBC_FAMILY="$("$PLATFORM" libc 2>/dev/null || printf unknown)"

printf 'Platform: %s %s\n' "$DIST" "$RELEASE"
printf 'Service framework: %s\n' "$INIT_SYSTEM"
printf 'Package manager: %s\n' "$PKG_MANAGER"
printf 'Package ABI: %s\n' "${PKG_ARCH:-unknown}"
printf 'Kernel machine: %s\n' "$KERNEL_ARCH"
printf 'libc: %s\n' "$LIBC_FAMILY"

if [ -f "$SCRIPT_DIR/../VERSION" ]; then
    cp "$SCRIPT_DIR/../VERSION" "$LIB_DIR/VERSION"
else
    curl -fsSL "$RAW_BASE/VERSION" -o "$LIB_DIR/VERSION"
fi
chmod 0644 "$LIB_DIR/VERSION"

# The router never compiles the mapper. An explicit/local mapper is target-
# smoke-tested and recorded as local; otherwise only a published Release asset
# selected by exact Package ABI and verified by SHA-256 is accepted. Failure to
# obtain a released mapper is non-fatal: Direct/Gate remain available.
MAPPER_INSTALLER="$LIB_DIR/remote-gate-mapper-install.sh"
MAPPER_EXPLICIT_SOURCE="${REMOTE_GATE_MAPPER_SOURCE:-}"
MAPPER_LOCAL_SOURCE="$SCRIPT_DIR/../native/remote-gate-mapper"
if [ -n "$MAPPER_EXPLICIT_SOURCE" ]; then
    sh "$MAPPER_INSTALLER" install-local "$MAPPER_EXPLICIT_SOURCE" || fail "Explicit mapper binary failed validation."
elif [ -f "$MAPPER_LOCAL_SOURCE" ] && [ -x "$MAPPER_LOCAL_SOURCE" ]; then
    sh "$MAPPER_INSTALLER" install-local "$MAPPER_LOCAL_SOURCE" || fail "Local mapper binary failed validation."
else
    if sh "$MAPPER_INSTALLER" install-release; then
        :
    else
        mapper_rc=$?
        if [ "$mapper_rc" -eq 3 ]; then
            printf 'WARN: No released mapper is available for this exact Package ABI; Mapped Access stays unavailable.\n' >&2
        else
            printf 'WARN: Released mapper validation failed; Mapped Access stays unavailable.\n' >&2
        fi
    fi
fi

BACKEND="$("$LIB_DIR/remote-gate-firewall.sh" detect 2>/dev/null)" || fail "Unsupported firewall capability. Need fw4+nftables or fw3+iptables+ipset."
case "$BACKEND" in
    fw4-nftables) printf 'Detected firewall backend: firewall4 / nftables\n' ;;
    fw3-iptables) printf 'Detected firewall backend: firewall3 / iptables + ipset\n' ;;
    *) fail "Unsupported firewall backend: $BACKEND" ;;
esac

IPV6_CAPABLE=no
if "$LIB_DIR/remote-gate-firewall.sh" ipv6-capable >/dev/null 2>&1; then IPV6_CAPABLE=yes; fi
MAPPER_AVAILABLE=no
if sh "$MAPPER_INSTALLER" current >/dev/null 2>&1; then MAPPER_AVAILABLE=yes; fi
printf 'IPv6 Gate firewall capability: %s\n' "$IPV6_CAPABLE"
printf 'Mapped Access mapper integrity current: %s\n' "$MAPPER_AVAILABLE"
printf 'Remote Gate controls only registered router INPUT ingress and optional Ping Echo on protected WAN endpoints.\n'
printf 'FORWARD, DNAT, UPnP, NAT-PMP, qBittorrent and unrelated ports are not filtered by the Access Gate.\n\n'

cat > "$CONFIG_FILE" <<CFGEOF
HOSTNAME='$HOSTNAME'
WRITE_TOKEN='$WRITE_TOKEN'
AGENT_INTERFACE=''
AGENT_INTERVAL='10'
GATE_IPV6='auto'
CONTROL_TRANSPORT='auto'
MAPPED_ACCESS='auto'
CFGEOF
chmod 0600 "$CONFIG_FILE"
unset WRITE_TOKEN

cat > "$STATE_DIR/install-manifest" <<'MANIFEST'
schema=2
wireguard_owned=0
firewall_include_owned=1
agent_owned=1
mapper_owned=1
MANIFEST
chmod 0600 "$STATE_DIR/install-manifest"

"$LIB_DIR/remote-gate-firewall.sh" install >/dev/null
"$LIB_DIR/remote-gate-agent.sh" sync-firewall || fail "Initial Multi-WAN/service firewall policy sync failed."

if [ "$BACKEND" = "fw3-iptables" ]; then
    printf '\nIPv4 INPUT head:\n'; iptables -S INPUT | sed -n '1,4p'
    if command -v ip6tables >/dev/null 2>&1; then printf '\nIPv6 INPUT head:\n'; ip6tables -S INPUT | sed -n '1,4p'; fi
else
    fw4 -q check
fi

grep -Fqx "$CRON_LINE" /etc/crontabs/root 2>/dev/null || printf '%s\n' "$CRON_LINE" >> /etc/crontabs/root
if [ -x /etc/init.d/cron ]; then /etc/init.d/cron restart >/dev/null 2>&1 || true; fi

"$INIT_FILE" enable
"$INIT_FILE" stop >/dev/null 2>&1 || true
"$INIT_FILE" start || fail "Remote Gate agent failed to start."
"$LIB_DIR/remote-gate-egress-probe.sh" >/dev/null 2>&1 || true
"$LIB_DIR/remote-gate-agent.sh" report || true

printf '\nWeiG Remote Gate OpenWrt-family components installed.\n'
printf 'Platform: %s %s | service=%s | package=%s | ABI=%s\n' "$DIST" "$RELEASE" "$INIT_SYSTEM" "$PKG_MANAGER" "${PKG_ARCH:-unknown}"
printf 'Firewall backend: %s\n' "$BACKEND"
printf 'IPv6 Gate: auto (%s firewall capability)\n' "$IPV6_CAPABLE"
printf 'Mapped Access: %s\n' "$([ "$MAPPER_AVAILABLE" = yes ] && printf 'available when NAT behavior permits UDP mapping' || printf 'unavailable until a current exact-ABI Remote Gate mapper passes integrity validation')"
printf 'Control transport: automatic IPv4/IPv6 Multi-WAN health fallback\n'
printf 'Private/CGNAT WAN IPv4 egress: best-effort per-WAN probe enabled\n'
printf 'The WAN has no HTTP/HTTPS listener from this project.\n'
printf 'qBittorrent/BT port forwarding remains under the original firewall and is unaffected.\n'
printf 'Safe update: %s/update.sh\n' "$LIB_DIR"
printf 'Read-only audit: %s/remote-gate-audit.sh\n' "$LIB_DIR"
printf 'Platform audit: %s summary\n' "$PLATFORM"
printf 'Mapper delivery audit: %s/remote-gate-mapper-install.sh status-json\n' "$LIB_DIR"
printf 'Mapped Access status: %s/remote-gate-mapping.sh status-json\n' "$LIB_DIR"
printf 'Optional WG home Internet egress: %s/remote-gate-wireguard-egress.sh status-json\n' "$LIB_DIR"
printf 'Safe uninstall: %s/uninstall.sh --dry-run\n' "$LIB_DIR"
printf 'Firewall status: %s/remote-gate-firewall.sh status-json\n' "$LIB_DIR"
