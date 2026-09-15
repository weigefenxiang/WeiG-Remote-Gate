#!/bin/sh
set -eu
umask 077

CONFIG_FILE="/etc/remote-gate.conf"
STATE_DIR="/etc/remote-gate-state/wg-profiles"
RUNTIME_DIR="${REMOTE_GATE_RUNTIME_DIR:-/tmp/remote-gate}/profile-exports"
SERVICES="/usr/lib/remote-gate/remote-gate-service-registry.sh"
TAG="remote-gate-profiles"

[ -r "$CONFIG_FILE" ] || { echo "ERROR: missing $CONFIG_FILE" >&2; exit 1; }
# shellcheck disable=SC1090
. "$CONFIG_FILE"

WG_PROFILE_IPV4_POOL="${WG_PROFILE_IPV4_POOL:-}"
WG_PROFILE_HOME_NETWORKS="${WG_PROFILE_HOME_NETWORKS:-}"
WG_PROFILE_DNS="${WG_PROFILE_DNS:-}"
WG_PROFILE_MTU="${WG_PROFILE_MTU:-}"
WG_PROFILE_PERSISTENT_KEEPALIVE="${WG_PROFILE_PERSISTENT_KEEPALIVE:-25}"

mkdir -p "$STATE_DIR" "$RUNTIME_DIR"
chmod 700 "$STATE_DIR" "$RUNTIME_DIR" 2>/dev/null || true

valid_name() { case "$1" in ''|*[!A-Za-z0-9_.:@+-]*) return 1 ;; *) return 0 ;; esac; }
valid_id() { printf '%s\n' "$1" | grep -Eq '^[a-f0-9]{24}$'; }
valid_command_id() { printf '%s\n' "$1" | grep -Eq '^[a-f0-9]{32}$'; }
valid_profile_name() { printf '%s\n' "$1" | grep -Eq '^[A-Za-z0-9_. +()-]{1,48}$'; }
valid_uint() { case "$1" in ''|*[!0-9]*) return 1 ;; *) return 0 ;; esac; }
valid_port() { valid_uint "$1" && [ "$1" -ge 1 ] && [ "$1" -le 65535 ]; }
valid_keepalive() { valid_uint "$1" && [ "$1" -ge 0 ] && [ "$1" -le 300 ]; }
valid_ipv4() {
    printf '%s\n' "$1" | awk -F. '
        BEGIN { ok=1 }
        NF != 4 { ok=0 }
        {
            for (i=1; i<=4; i++) {
                if ($i !~ /^[0-9]+$/ || $i < 0 || $i > 255) ok=0
            }
        }
        END { exit ok ? 0 : 1 }
    '
}
valid_ipv6() {
    case "$1" in
        *:*) printf '%s\n' "$1" | grep -Eq '^[0-9A-Fa-f:]+$' ;;
        *) return 1 ;;
    esac
}
valid_key() { printf '%s\n' "$1" | grep -Eq '^[A-Za-z0-9+/]{43}=$'; }

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/[[:cntrl:]]/ /g'
}

cidr_network() {
    cidr="$1"
    case "$cidr" in */*) ;; *) return 1 ;; esac
    ip="${cidr%/*}"; prefix="${cidr#*/}"
    valid_ipv4 "$ip" || return 1
    valid_uint "$prefix" && [ "$prefix" -ge 20 ] && [ "$prefix" -le 30 ] || return 1
    awk -v ip="$ip" -v prefix="$prefix" '
        function i2n(n) { return int(n/16777216)%256 "." int(n/65536)%256 "." int(n/256)%256 "." n%256 }
        BEGIN {
            split(ip,a,"."); n=a[1]*16777216+a[2]*65536+a[3]*256+a[4]
            block=2^(32-prefix); base=int(n/block)*block
            print i2n(base) "/" prefix
        }
    '
}

infer_pool() {
    wg="$1"
    if [ -n "$WG_PROFILE_IPV4_POOL" ]; then
        cidr_network "$WG_PROFILE_IPV4_POOL"
        return
    fi
    current="$(ip -o -4 addr show dev "$wg" 2>/dev/null | awk 'NR==1{print $4}')"
    [ -n "$current" ] || return 1
    cidr_network "$current"
}

collect_used_ipv4() {
    wg="$1"; out="$2"
    : > "$out"
    ip -o -4 addr show dev "$wg" 2>/dev/null | awk '{split($4,a,"/"); if (a[1] ~ /^[0-9]+\./) print a[1] "/32"}' >> "$out" || true
    wg show "$wg" allowed-ips 2>/dev/null | awk '{
        for (i=2; i<=NF; i++) {
            n=split($i,a,",")
            for (j=1; j<=n; j++) if (a[j] ~ /^[0-9]+\./) print a[j]
        }
    }' >> "$out" || true
    for meta in "$STATE_DIR"/*.json; do
        [ -f "$meta" ] || continue
        jsonfilter -i "$meta" -e '@.client_address' 2>/dev/null | sed -n '1p' >> "$out" || true
    done
    sed '/^$/d' "$out" | sort -u > "${out}.tmp"
    mv "${out}.tmp" "$out"
}

ipv4_is_used() {
    candidate="$1"; used="$2"
    awk -v candidate="$candidate" '
        function ipn(v, a){split(v,a,"."); return a[1]*16777216+a[2]*65536+a[3]*256+a[4]}
        BEGIN { c=ipn(candidate); found=0 }
        {
            split($0,p,"/"); if (p[1] !~ /^[0-9]+\./) next
            prefix=(p[2] == "" ? 32 : p[2]+0)
            if (prefix < 0 || prefix > 32) next
            block=2^(32-prefix); base=int(ipn(p[1])/block)*block
            if (c >= base && c < base+block) { found=1; exit }
        }
        END { exit found ? 0 : 1 }
    ' "$used"
}

allocate_ipv4() {
    wg="$1"; pool="$2"; used="$RUNTIME_DIR/used.$$"
    collect_used_ipv4 "$wg" "$used"
    ip="${pool%/*}"; prefix="${pool#*/}"
    awk -v ip="$ip" -v prefix="$prefix" '
        function i2n(n) { return int(n/16777216)%256 "." int(n/65536)%256 "." int(n/256)%256 "." n%256 }
        BEGIN {
            split(ip,a,"."); n=a[1]*16777216+a[2]*65536+a[3]*256+a[4]
            block=2^(32-prefix); base=int(n/block)*block; last=base+block-1
            for (x=base+1; x<last; x++) print i2n(x)
        }
    ' | while IFS= read -r candidate; do
        if ! ipv4_is_used "$candidate" "$used"; then
            printf '%s\n' "$candidate"
            break
        fi
    done
    rm -f "$used"
}

lan_values() {
    status="$(ubus call network.interface.lan status 2>/dev/null || true)"
    [ -n "$status" ] || return 0
    address="$(printf '%s' "$status" | jsonfilter -e '@["ipv4-address"][0].address' 2>/dev/null | sed -n '1p')"
    mask="$(printf '%s' "$status" | jsonfilter -e '@["ipv4-address"][0].mask' 2>/dev/null | sed -n '1p')"
    if valid_ipv4 "$address" && valid_uint "$mask"; then
        network="$(cidr_network "$address/$mask" 2>/dev/null || true)"
        [ -n "$network" ] && printf '%s|%s\n' "$address" "$network"
    fi
}

home_networks() {
    pool="$1"
    if [ -n "$WG_PROFILE_HOME_NETWORKS" ]; then
        printf '%s\n' "$WG_PROFILE_HOME_NETWORKS" | tr ',' '\n' | sed '/^$/d' | awk '!seen[$0]++' | paste -sd, -
        return
    fi
    lan="$(lan_values | sed -n '1p')"
    lan_network=""
    case "$lan" in *'|'*) lan_network="${lan#*|}" ;; esac
    {
        [ -n "$lan_network" ] && printf '%s\n' "$lan_network"
        printf '%s\n' "$pool"
    } | awk 'NF && !seen[$0]++' | paste -sd, -
}

profile_dns() {
    if [ -n "$WG_PROFILE_DNS" ]; then printf '%s\n' "$WG_PROFILE_DNS"; return; fi
    lan="$(lan_values | sed -n '1p')"
    case "$lan" in *'|'*) printf '%s\n' "${lan%%|*}" ;; esac
}

csv_json_array() {
    csv="$1"; first=1
    printf '['
    oldifs="$IFS"; IFS=','
    for value in $csv; do
        [ -n "$value" ] || continue
        [ "$first" -eq 1 ] || printf ','
        first=0
        printf '"%s"' "$(json_escape "$value")"
    done
    IFS="$oldifs"
    printf ']'
}

metadata_file() { printf '%s/%s.json\n' "$STATE_DIR" "$1"; }
result_file() { printf '%s/%s.json\n' "$RUNTIME_DIR" "$1"; }

owned_section() {
    profile_id="$1"; wg_name="$2"; public_key="$3"; section="$4"
    section_type="$(uci -q get "network.$section" 2>/dev/null || true)"
    description="$(uci -q get "network.$section.description" 2>/dev/null || true)"
    persisted_key="$(uci -q get "network.$section.public_key" 2>/dev/null || true)"
    [ "$section_type" = "wireguard_${wg_name}" ] && [ "$description" = "remote-gate:${profile_id}" ] && [ "$persisted_key" = "$public_key" ]
}

cleanup_created_peer() {
    wg_name="$1"; public_key="$2"; section="$3"
    if command -v wg >/dev/null 2>&1 && wg show interfaces 2>/dev/null | tr ' ' '\n' | grep -Fxq "$wg_name"; then
        wg set "$wg_name" peer "$public_key" remove >/dev/null 2>&1 || true
    fi
    uci -q delete "network.$section" >/dev/null 2>&1 || true
    uci commit network >/dev/null 2>&1 || true
}

revoke_profile() {
    profile_id="$1"
    valid_id "$profile_id" || { echo 'ERROR: invalid-profile-id' >&2; return 1; }
    meta="$(metadata_file "$profile_id")"
    [ -r "$meta" ] || return 0
    wg_name="$(jsonfilter -i "$meta" -e '@.wireguard' 2>/dev/null | sed -n '1p')"
    public_key="$(jsonfilter -i "$meta" -e '@.public_key' 2>/dev/null | sed -n '1p')"
    section="$(jsonfilter -i "$meta" -e '@.uci_section' 2>/dev/null | sed -n '1p')"
    valid_name "$wg_name" && valid_key "$public_key" && valid_name "$section" || { echo 'ERROR: invalid-profile-metadata' >&2; return 1; }
    owned_section "$profile_id" "$wg_name" "$public_key" "$section" || { echo 'ERROR: profile-ownership-mismatch' >&2; return 1; }

    if command -v wg >/dev/null 2>&1 && wg show interfaces 2>/dev/null | tr ' ' '\n' | grep -Fxq "$wg_name"; then
        wg set "$wg_name" peer "$public_key" remove >/dev/null 2>&1 || { echo 'ERROR: wireguard-peer-remove-failed' >&2; return 1; }
    fi
    uci -q delete "network.$section" >/dev/null 2>&1 || { echo 'ERROR: wireguard-peer-persist-remove-failed' >&2; return 1; }
    uci commit network >/dev/null 2>&1 || { echo 'ERROR: wireguard-peer-persist-remove-failed' >&2; return 1; }
    rm -f "$meta"
    logger -t "$TAG" "revoked managed peer id=$profile_id wg=$wg_name" 2>/dev/null || true
}

create_profile() {
    command_id="$1"; profile_id="$2"; profile_name="$3"; wg_name="$4"; route_mode="$5"
    endpoint_family="$6"; endpoint_address="$7"; endpoint_port="$8"; access_method="$9"
    shift 9
    service_id="$1"; service_port="$2"; keepalive="$3"

    valid_command_id "$command_id" && valid_id "$profile_id" && valid_profile_name "$profile_name" || { echo 'ERROR: invalid-profile-identity' >&2; return 1; }
    valid_name "$wg_name" && valid_name "$service_id" || { echo 'ERROR: invalid-wireguard-service' >&2; return 1; }
    [ "$service_id" = "wg.$wg_name" ] || { echo 'ERROR: service-wireguard-mismatch' >&2; return 1; }
    [ "$route_mode" = home ] || [ "$route_mode" = full ] || { echo 'ERROR: invalid-route-mode' >&2; return 1; }
    [ "$endpoint_family" = ipv4 ] || [ "$endpoint_family" = ipv6 ] || { echo 'ERROR: invalid-endpoint-family' >&2; return 1; }
    case "$access_method" in direct|mapped) ;; *) echo 'ERROR: invalid-access-method' >&2; return 1 ;; esac
    if [ "$endpoint_family" = ipv4 ]; then
        valid_ipv4 "$endpoint_address" || { echo 'ERROR: invalid-endpoint-address' >&2; return 1; }
    else
        valid_ipv6 "$endpoint_address" || { echo 'ERROR: invalid-endpoint-address' >&2; return 1; }
    fi
    valid_port "$endpoint_port" && valid_port "$service_port" && valid_keepalive "$keepalive" || { echo 'ERROR: invalid-profile-port-or-keepalive' >&2; return 1; }
    command -v wg >/dev/null 2>&1 || { echo 'ERROR: wg-command-unavailable' >&2; return 1; }
    [ "$service_port" = "$(wg show "$wg_name" listen-port 2>/dev/null | sed -n '1p')" ] || { echo 'ERROR: wireguard-listen-port-changed' >&2; return 1; }
    [ -x "$SERVICES" ] && "$SERVICES" validate "$service_id" udp "$service_port" >/dev/null 2>&1 || { echo 'ERROR: service-not-registered' >&2; return 1; }

    saved_result="$(result_file "$command_id")"
    if [ -s "$saved_result" ]; then cat "$saved_result"; return 0; fi
    meta="$(metadata_file "$profile_id")"
    [ ! -e "$meta" ] || { echo 'ERROR: profile-already-exists' >&2; return 1; }

    pool="$(infer_pool "$wg_name" 2>/dev/null || true)"
    [ -n "$pool" ] || { echo 'ERROR: profile-ipv4-pool-unavailable' >&2; return 1; }
    client_ip="$(allocate_ipv4 "$wg_name" "$pool" | sed -n '1p')"
    valid_ipv4 "$client_ip" || { echo 'ERROR: profile-ipv4-pool-exhausted' >&2; return 1; }

    private_key="$(wg genkey 2>/dev/null)"
    valid_key "$private_key" || { echo 'ERROR: client-key-generation-failed' >&2; return 1; }
    public_key="$(printf '%s\n' "$private_key" | wg pubkey 2>/dev/null)"
    server_public_key="$(wg show "$wg_name" public-key 2>/dev/null | sed -n '1p')"
    valid_key "$public_key" && valid_key "$server_public_key" || { echo 'ERROR: wireguard-key-unavailable' >&2; return 1; }

    section="rgp_${profile_id}"
    wg set "$wg_name" peer "$public_key" allowed-ips "$client_ip/32" || { echo 'ERROR: wireguard-peer-apply-failed' >&2; return 1; }

    if ! {
        uci -q delete "network.$section" >/dev/null 2>&1 || true
        uci set "network.$section=wireguard_${wg_name}"
        uci set "network.$section.description=remote-gate:${profile_id}"
        uci set "network.$section.public_key=$public_key"
        uci set "network.$section.route_allowed_ips=1"
        uci add_list "network.$section.allowed_ips=$client_ip/32"
        uci commit network
    }; then
        cleanup_created_peer "$wg_name" "$public_key" "$section"
        echo 'ERROR: wireguard-peer-persist-failed' >&2
        return 1
    fi

    created_at="$(date +%s)"
    networks="$(home_networks "$pool")"
    dns="$(profile_dns)"
    mtu="$WG_PROFILE_MTU"
    if [ -n "$mtu" ]; then valid_uint "$mtu" && [ "$mtu" -ge 576 ] && [ "$mtu" -le 9000 ] || mtu=""; fi
    networks_json="$(csv_json_array "$networks")"

    meta_tmp="${meta}.tmp.$$"
    if ! cat > "$meta_tmp" <<EOF
{"schema":1,"id":"$profile_id","name":"$(json_escape "$profile_name")","wireguard":"$wg_name","public_key":"$public_key","client_address":"$client_ip/32","route_mode":"$route_mode","endpoint_family":"$endpoint_family","access_method":"$access_method","endpoint_address":"$(json_escape "$endpoint_address")","endpoint_port":$endpoint_port,"persistent_keepalive":$keepalive,"home_networks":$networks_json,"created_at":$created_at,"uci_section":"$section"}
EOF
    then
        rm -f "$meta_tmp"
        cleanup_created_peer "$wg_name" "$public_key" "$section"
        echo 'ERROR: profile-metadata-write-failed' >&2
        return 1
    fi
    if ! chmod 600 "$meta_tmp" || ! mv -f "$meta_tmp" "$meta"; then
        rm -f "$meta_tmp" "$meta"
        cleanup_created_peer "$wg_name" "$public_key" "$section"
        echo 'ERROR: profile-metadata-write-failed' >&2
        return 1
    fi

    result_tmp="${saved_result}.tmp.$$"
    mtu_json=null; [ -n "$mtu" ] && mtu_json="$mtu"
    if ! cat > "$result_tmp" <<EOF
{"schema":1,"command_id":"$command_id","profile":{"id":"$profile_id","name":"$(json_escape "$profile_name")","wireguard":"$wg_name","client_address":"$client_ip/32","private_key":"$private_key","public_key":"$public_key","server_public_key":"$server_public_key","endpoint_family":"$endpoint_family","endpoint_address":"$(json_escape "$endpoint_address")","endpoint_port":$endpoint_port,"access_method":"$access_method","route_mode":"$route_mode","home_networks":$networks_json,"dns":"$(json_escape "$dns")","mtu":$mtu_json,"persistent_keepalive":$keepalive,"created_at":$created_at}}
EOF
    then
        rm -f "$result_tmp"
        revoke_profile "$profile_id" >/dev/null 2>&1 || true
        echo 'ERROR: profile-export-write-failed' >&2
        return 1
    fi
    chmod 600 "$result_tmp" || { rm -f "$result_tmp"; revoke_profile "$profile_id" >/dev/null 2>&1 || true; echo 'ERROR: profile-export-write-failed' >&2; return 1; }
    mv -f "$result_tmp" "$saved_result" || { rm -f "$result_tmp"; revoke_profile "$profile_id" >/dev/null 2>&1 || true; echo 'ERROR: profile-export-write-failed' >&2; return 1; }

    logger -t "$TAG" "created managed peer id=$profile_id wg=$wg_name address=$client_ip endpoint_family=$endpoint_family access_method=$access_method" 2>/dev/null || true
    cat "$saved_result"
}

list_json() {
    first=1
    printf '['
    for meta in "$STATE_DIR"/*.json; do
        [ -f "$meta" ] || continue
        base="${meta##*/}"; id="${base%.json}"
        valid_id "$id" || continue
        [ "$first" -eq 1 ] || printf ','
        first=0
        cat "$meta"
    done
    printf ']'
}

case "${1:-}" in
    create)
        [ "$#" -eq 13 ] || { echo 'usage: create command_id profile_id name wg route_mode endpoint_family endpoint_address endpoint_port access_method service_id service_port keepalive' >&2; exit 2; }
        shift
        create_profile "$@"
        ;;
    revoke)
        [ "$#" -eq 2 ] || exit 2
        revoke_profile "$2"
        ;;
    revoke-all)
        for meta in "$STATE_DIR"/*.json; do
            [ -f "$meta" ] || continue
            id="${meta##*/}"; id="${id%.json}"
            revoke_profile "$id" || exit 1
        done
        ;;
    list-json) list_json ;;
    result)
        [ "$#" -eq 2 ] && valid_command_id "$2" || exit 2
        file="$(result_file "$2")"; [ -r "$file" ] || exit 1; cat "$file"
        ;;
    clear-result)
        [ "$#" -eq 2 ] && valid_command_id "$2" || exit 2
        rm -f "$(result_file "$2")"
        ;;
    clear-results) rm -f "$RUNTIME_DIR"/*.json 2>/dev/null || true ;;
    *) echo "usage: $0 create|revoke|revoke-all|list-json|result|clear-result|clear-results" >&2; exit 2 ;;
esac
