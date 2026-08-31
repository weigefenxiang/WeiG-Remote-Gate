# Sourced by remote-gate-firewall.sh.
write_fw4_includes() {
    local rg_auto
    rg_auto="$(uci -q get firewall.@defaults[0].auto_includes 2>/dev/null || true)"
    [ "$rg_auto" != "0" ] || fail "firewall auto_includes=0; fw4 backend requires automatic nft includes"
    mkdir -p "$(dirname "$FW4_TABLE_INCLUDE")" "$(dirname "$FW4_INPUT_INCLUDE")"
    cat > "$FW4_TABLE_INCLUDE" <<'NFT'
set weig_remote_gate_protected_ifname_v4 { type ifname; }
set weig_remote_gate_protected_ifname_v6 { type ifname; }
set weig_remote_gate_protected_udp_port { type inet_service; }

set weig_remote_gate_auth_ipv4 { type ipv4_addr; flags timeout; }
set weig_remote_gate_auth_ipv6 { type ipv6_addr; flags timeout; }
set weig_remote_gate_auth_ifname_v4 { type ifname; }
set weig_remote_gate_auth_ifname_v6 { type ifname; }
set weig_remote_gate_auth_ping_ifname_v4 { type ifname; }
set weig_remote_gate_auth_ping_ifname_v6 { type ifname; }
set weig_remote_gate_auth_udp_port_v4 { type inet_service; }
set weig_remote_gate_auth_udp_port_v6 { type inet_service; }

set weig_remote_gate_verify_ipv4 { type ipv4_addr; flags interval,timeout; }
set weig_remote_gate_verify_ipv6 { type ipv6_addr; flags interval,timeout; }
set weig_remote_gate_verify_ifname_v4 { type ifname; }
set weig_remote_gate_verify_ifname_v6 { type ifname; }
set weig_remote_gate_verify_udp_port_v4 { type inet_service; }
set weig_remote_gate_verify_udp_port_v6 { type inet_service; }
NFT
    cat > "$FW4_INPUT_INCLUDE" <<'NFT'
iifname @weig_remote_gate_verify_ifname_v4 ip saddr @weig_remote_gate_verify_ipv4 udp dport @weig_remote_gate_verify_udp_port_v4 counter accept comment "!WeiG Remote Gate: IPv4 verification window"
iifname @weig_remote_gate_auth_ping_ifname_v4 ip saddr @weig_remote_gate_auth_ipv4 icmp type echo-request counter accept comment "!WeiG Remote Gate: authorized IPv4 ICMP"
iifname @weig_remote_gate_protected_ifname_v4 icmp type echo-request counter drop comment "!WeiG Remote Gate: protected IPv4 ICMP"
iifname @weig_remote_gate_auth_ifname_v4 ip saddr @weig_remote_gate_auth_ipv4 udp dport @weig_remote_gate_auth_udp_port_v4 counter accept comment "!WeiG Remote Gate: authorized IPv4 WireGuard"
iifname @weig_remote_gate_protected_ifname_v4 udp dport @weig_remote_gate_protected_udp_port counter drop comment "!WeiG Remote Gate: protected IPv4 WireGuard"

iifname @weig_remote_gate_verify_ifname_v6 ip6 saddr @weig_remote_gate_verify_ipv6 udp dport @weig_remote_gate_verify_udp_port_v6 counter accept comment "!WeiG Remote Gate: IPv6 verification window"
iifname @weig_remote_gate_auth_ping_ifname_v6 ip6 saddr @weig_remote_gate_auth_ipv6 icmpv6 type echo-request counter accept comment "!WeiG Remote Gate: authorized IPv6 ICMP"
iifname @weig_remote_gate_protected_ifname_v6 icmpv6 type echo-request counter drop comment "!WeiG Remote Gate: protected IPv6 ICMP"
iifname @weig_remote_gate_auth_ifname_v6 ip6 saddr @weig_remote_gate_auth_ipv6 udp dport @weig_remote_gate_auth_udp_port_v6 counter accept comment "!WeiG Remote Gate: authorized IPv6 WireGuard"
iifname @weig_remote_gate_protected_ifname_v6 udp dport @weig_remote_gate_protected_udp_port counter drop comment "!WeiG Remote Gate: protected IPv6 WireGuard"
NFT
}

fw4_check_order() {
    local rg_rendered rg_gate_line rg_state_line
    rg_rendered="$(fw4 -q print)" || return 1
    rg_gate_line="$(printf '%s\n' "$rg_rendered" | grep -n '!WeiG Remote Gate: protected IPv4 ICMP' | sed -n '1s/:.*//p')"
    [ -n "$rg_gate_line" ] || rg_gate_line="$(printf '%s\n' "$rg_rendered" | grep -n '!WeiG Remote Gate: protected IPv6 ICMP' | sed -n '1s/:.*//p')"
    rg_state_line="$(printf '%s\n' "$rg_rendered" | grep -n '!fw4: Handle inbound flows' | sed -n '1s/:.*//p')"
    [ -n "$rg_gate_line" ] && [ -n "$rg_state_line" ] && [ "$rg_gate_line" -lt "$rg_state_line" ]
}

fw3_ensure_set() {
    local rg_name="$1" rg_type="$2" rg_family="$3"
    ipset list "$rg_name" >/dev/null 2>&1 && return 0
    ipset create "$rg_name" "$rg_type" family "$rg_family" timeout 1800 >/dev/null
}
fw3_ensure_sets() {
    fw3_ensure_set "$FW3_AUTH_SET_V4" hash:ip inet
    fw3_ensure_set "$FW3_VERIFY_SET_V4" hash:net inet
    if fw3_ipv6_capable; then
        fw3_ensure_set "$FW3_AUTH_SET_V6" hash:ip inet6
        fw3_ensure_set "$FW3_VERIFY_SET_V6" hash:net inet6
    fi
}

read_auth_record_file() {
    local rg_family="$1" rg_file="$2" rg_ip rg_dev rg_port rg_expires rg_file_family rg_scope rg_kind rg_now rg_remaining
    [ -r "$rg_file" ] || return 1
    rg_ip="$(sed -n '1p' "$rg_file")"; rg_dev="$(sed -n '2p' "$rg_file")"; rg_port="$(sed -n '3p' "$rg_file")"
    rg_expires="$(sed -n '4p' "$rg_file")"; rg_file_family="$(sed -n '5p' "$rg_file")"; rg_scope="$(sed -n '6p' "$rg_file")"; rg_kind="$(sed -n '7p' "$rg_file")"
    [ -n "$rg_file_family" ] || rg_file_family="$rg_family"
    [ -n "$rg_scope" ] || rg_scope=wg_ping
    [ -n "$rg_kind" ] || rg_kind=legacy
    rg_now="$(date +%s)"
    valid_family "$rg_file_family" && [ "$rg_file_family" = "$rg_family" ] || { rm -f "$rg_file"; return 1; }
    valid_scope "$rg_scope" || { rm -f "$rg_file"; return 1; }
    valid_source_kind "$rg_kind" || { rm -f "$rg_file"; return 1; }
    case "$rg_family" in ipv4) valid_ipv4 "$rg_ip" ;; ipv6) valid_ipv6 "$rg_ip" ;; esac || { rm -f "$rg_file"; return 1; }
    valid_device "$rg_dev" && valid_uint "$rg_port" && valid_uint "$rg_expires" && [ "$rg_expires" -gt "$rg_now" ] || { rm -f "$rg_file"; return 1; }
    rg_remaining="$((rg_expires - rg_now))"
    printf '%s %s %s %s %s %s\n' "$rg_ip" "$rg_dev" "$rg_port" "$rg_expires" "$rg_remaining" "$rg_scope:$rg_kind"
}
read_auth_records() {
    local rg_family="$1" rg_dir rg_file
    rg_dir="$(family_auth_dir "$rg_family")" || return 1
    [ -d "$rg_dir" ] || return 0
    for rg_file in "$rg_dir"/*; do
        [ -f "$rg_file" ] || continue
        read_auth_record_file "$rg_family" "$rg_file" 2>/dev/null || true
    done
}
read_auth_record() {
    read_auth_records "$1" | sed -n '1p'
}

read_verify_record() {
    local rg_family="$1" rg_file rg_source rg_dev rg_port rg_expires rg_file_family rg_mode rg_now rg_remaining
    rg_file="$(family_verify_file "$rg_family")" || return 1
    [ -r "$rg_file" ] || return 1
    rg_source="$(sed -n '1p' "$rg_file")"; rg_dev="$(sed -n '2p' "$rg_file")"; rg_port="$(sed -n '3p' "$rg_file")"
    rg_expires="$(sed -n '4p' "$rg_file")"; rg_file_family="$(sed -n '5p' "$rg_file")"; rg_mode="$(sed -n '6p' "$rg_file")"
    rg_now="$(date +%s)"
    [ "$rg_file_family" = "$rg_family" ] || { rm -f "$rg_file"; return 1; }
    case "$rg_mode" in candidate|discovery) ;; *) rm -f "$rg_file"; return 1 ;; esac
    valid_device "$rg_dev" && valid_uint "$rg_port" && valid_uint "$rg_expires" && [ "$rg_expires" -gt "$rg_now" ] || { rm -f "$rg_file"; return 1; }
    if [ "$rg_source" != "any" ]; then
        case "$rg_family" in ipv4) valid_ipv4 "$rg_source" ;; ipv6) valid_ipv6 "$rg_source" ;; esac || { rm -f "$rg_file"; return 1; }
    fi
    rg_remaining="$((rg_expires - rg_now))"
    printf '%s %s %s %s %s %s\n' "$rg_source" "$rg_dev" "$rg_port" "$rg_expires" "$rg_remaining" "$rg_mode"
}

auth_record_policy_current() {
    local rg_family="$1" rg_record="$2" rg_ip rg_dev rg_port rg_expires rg_remaining rg_meta rg_device_file
    [ -n "$rg_record" ] || return 1
    set -- $rg_record; rg_ip="$1"; rg_dev="$2"; rg_port="$3"; rg_expires="$4"; rg_remaining="$5"; rg_meta="$6"
    rg_device_file="$(family_device_file "$rg_family")"
    grep -Fqx "$rg_dev" "$rg_device_file" 2>/dev/null || return 1
    grep -Fqx "$rg_port" "$PORTS_FILE" 2>/dev/null || return 1
}
verify_policy_current() {
    local rg_family="$1" rg_record rg_source rg_dev rg_port rg_expires rg_remaining rg_mode rg_device_file
    rg_record="$(read_verify_record "$rg_family" 2>/dev/null || true)"; [ -n "$rg_record" ] || return 1
    set -- $rg_record; rg_source="$1"; rg_dev="$2"; rg_port="$3"; rg_expires="$4"; rg_remaining="$5"; rg_mode="$6"
    rg_device_file="$(family_device_file "$rg_family")"
    grep -Fqx "$rg_dev" "$rg_device_file" 2>/dev/null || return 1
    grep -Fqx "$rg_port" "$PORTS_FILE" 2>/dev/null || return 1
}
reconcile_family() {
    local rg_family="$1" rg_dir rg_file rg_record rg_first="" rg_first_dev="" rg_first_port="" rg_first_scope="" rg_ip rg_dev rg_port rg_expires rg_remaining rg_meta rg_scope rg_verify
    rg_dir="$(family_auth_dir "$rg_family")"
    for rg_file in "$rg_dir"/*; do
        [ -f "$rg_file" ] || continue
        rg_record="$(read_auth_record_file "$rg_family" "$rg_file" 2>/dev/null || true)"
        [ -n "$rg_record" ] || continue
        if ! auth_record_policy_current "$rg_family" "$rg_record"; then
            logger -t "$TAG" "$rg_family authorization revoked because protected WAN/port policy changed" 2>/dev/null || true
            rm -f "$rg_file"
            continue
        fi
        set -- $rg_record; rg_ip="$1"; rg_dev="$2"; rg_port="$3"; rg_expires="$4"; rg_remaining="$5"; rg_meta="$6"; rg_scope="${rg_meta%%:*}"
        if [ -z "$rg_first" ]; then
            rg_first=1; rg_first_dev="$rg_dev"; rg_first_port="$rg_port"; rg_first_scope="$rg_scope"
        elif [ "$rg_dev" != "$rg_first_dev" ] || [ "$rg_port" != "$rg_first_port" ] || [ "$rg_scope" != "$rg_first_scope" ]; then
            logger -t "$TAG" "$rg_family authorization revoked because concurrent authorization profile differed" 2>/dev/null || true
            rm -f "$rg_file"
        fi
    done
    rg_verify="$(family_verify_file "$rg_family")"
    if [ -e "$rg_verify" ] && ! verify_policy_current "$rg_family"; then rm -f "$rg_verify"; fi
}
reconcile_policy() { reconcile_family ipv4; reconcile_family ipv6; }

fw3_remove_jump_v4() { while iptables -C INPUT -j "$FW3_CHAIN_V4" >/dev/null 2>&1; do iptables -D INPUT -j "$FW3_CHAIN_V4" >/dev/null 2>&1 || break; done; }
fw3_remove_jump_v6() { command -v ip6tables >/dev/null 2>&1 || return 0; while ip6tables -C INPUT -j "$FW3_CHAIN_V6" >/dev/null 2>&1; do ip6tables -D INPUT -j "$FW3_CHAIN_V6" >/dev/null 2>&1 || break; done; }

fw3_load_verify() {
    local rg_family="$1" rg_record rg_source rg_dev rg_port rg_expires rg_remaining rg_mode rg_set rg_chain rg_cmd rg_network
    rg_record="$(read_verify_record "$rg_family" 2>/dev/null || true)"; [ -n "$rg_record" ] || return 0
    set -- $rg_record; rg_source="$1"; rg_dev="$2"; rg_port="$3"; rg_expires="$4"; rg_remaining="$5"; rg_mode="$6"
    if [ "$rg_family" = ipv4 ]; then rg_set="$FW3_VERIFY_SET_V4"; rg_chain="$FW3_CHAIN_V4"; rg_cmd=iptables; [ "$rg_source" = any ] && rg_network=0.0.0.0/0 || rg_network="$rg_source/32"; else rg_set="$FW3_VERIFY_SET_V6"; rg_chain="$FW3_CHAIN_V6"; rg_cmd=ip6tables; [ "$rg_source" = any ] && rg_network=::/0 || rg_network="$rg_source/128"; fi
    ipset -exist add "$rg_set" "$rg_network" timeout "$rg_remaining" >/dev/null
    "$rg_cmd" -A "$rg_chain" -i "$rg_dev" -p udp --dport "$rg_port" -m set --match-set "$rg_set" src -j ACCEPT
}

fw3_load_auth() {
    local rg_family="$1" rg_records rg_record rg_ip rg_dev rg_port rg_expires rg_remaining rg_meta rg_scope rg_set rg_chain rg_cmd rg_first=1
    rg_records="$(read_auth_records "$rg_family" 2>/dev/null || true)"; [ -n "$rg_records" ] || return 0
    if [ "$rg_family" = ipv4 ]; then rg_set="$FW3_AUTH_SET_V4"; rg_chain="$FW3_CHAIN_V4"; rg_cmd=iptables; else rg_set="$FW3_AUTH_SET_V6"; rg_chain="$FW3_CHAIN_V6"; rg_cmd=ip6tables; fi
    printf '%s\n' "$rg_records" | while IFS= read -r rg_record; do
        [ -n "$rg_record" ] || continue
        set -- $rg_record; rg_ip="$1"; rg_dev="$2"; rg_port="$3"; rg_expires="$4"; rg_remaining="$5"; rg_meta="$6"
        ipset -exist add "$rg_set" "$rg_ip" timeout "$rg_remaining" >/dev/null
    done
    rg_record="$(printf '%s\n' "$rg_records" | sed -n '1p')"
    set -- $rg_record; rg_ip="$1"; rg_dev="$2"; rg_port="$3"; rg_expires="$4"; rg_remaining="$5"; rg_meta="$6"; rg_scope="${rg_meta%%:*}"
    if [ "$rg_scope" = wg_ping ]; then
        if [ "$rg_family" = ipv4 ]; then "$rg_cmd" -A "$rg_chain" -i "$rg_dev" -p icmp --icmp-type echo-request -m set --match-set "$rg_set" src -j ACCEPT; else "$rg_cmd" -A "$rg_chain" -i "$rg_dev" -p ipv6-icmp --icmpv6-type echo-request -m set --match-set "$rg_set" src -j ACCEPT; fi
    fi
    "$rg_cmd" -A "$rg_chain" -i "$rg_dev" -p udp --dport "$rg_port" -m set --match-set "$rg_set" src -j ACCEPT
}

fw3_rebuild_v4() {
    local rg_dev rg_port
    iptables -N "$FW3_CHAIN_V4" >/dev/null 2>&1 || true
    fw3_remove_jump_v4; iptables -F "$FW3_CHAIN_V4"; iptables -I INPUT 1 -j "$FW3_CHAIN_V4"
    ipset flush "$FW3_AUTH_SET_V4" >/dev/null 2>&1 || true; ipset flush "$FW3_VERIFY_SET_V4" >/dev/null 2>&1 || true
    fw3_load_verify ipv4; fw3_load_auth ipv4
    while IFS= read -r rg_dev; do
        [ -n "$rg_dev" ] || continue; valid_device "$rg_dev" || continue
        iptables -A "$FW3_CHAIN_V4" -i "$rg_dev" -p icmp --icmp-type echo-request -j DROP
        while IFS= read -r rg_port; do [ -n "$rg_port" ] || continue; valid_uint "$rg_port" || continue; [ "$rg_port" -ge 1 ] && [ "$rg_port" -le 65535 ] || continue; iptables -A "$FW3_CHAIN_V4" -i "$rg_dev" -p udp --dport "$rg_port" -j DROP; done < "$PORTS_FILE"
    done < "$DEVICES_V4_FILE"
    iptables -A "$FW3_CHAIN_V4" -j RETURN
}
fw3_rebuild_v6() {
    local rg_dev rg_port
    fw3_ipv6_capable || { fw3_remove_jump_v6; return 0; }
    if [ ! -s "$DEVICES_V6_FILE" ]; then fw3_remove_jump_v6; ip6tables -F "$FW3_CHAIN_V6" >/dev/null 2>&1 || true; ip6tables -X "$FW3_CHAIN_V6" >/dev/null 2>&1 || true; ipset flush "$FW3_AUTH_SET_V6" >/dev/null 2>&1 || true; ipset flush "$FW3_VERIFY_SET_V6" >/dev/null 2>&1 || true; return 0; fi
    ip6tables -N "$FW3_CHAIN_V6" >/dev/null 2>&1 || true
    fw3_remove_jump_v6; ip6tables -F "$FW3_CHAIN_V6"; ip6tables -I INPUT 1 -j "$FW3_CHAIN_V6"
    ipset flush "$FW3_AUTH_SET_V6" >/dev/null 2>&1 || true; ipset flush "$FW3_VERIFY_SET_V6" >/dev/null 2>&1 || true
    fw3_load_verify ipv6; fw3_load_auth ipv6
    while IFS= read -r rg_dev; do
        [ -n "$rg_dev" ] || continue; valid_device "$rg_dev" || continue
        ip6tables -A "$FW3_CHAIN_V6" -i "$rg_dev" -p ipv6-icmp --icmpv6-type echo-request -j DROP
        while IFS= read -r rg_port; do [ -n "$rg_port" ] || continue; valid_uint "$rg_port" || continue; [ "$rg_port" -ge 1 ] && [ "$rg_port" -le 65535 ] || continue; ip6tables -A "$FW3_CHAIN_V6" -i "$rg_dev" -p udp --dport "$rg_port" -j DROP; done < "$PORTS_FILE"
    done < "$DEVICES_V6_FILE"
    ip6tables -A "$FW3_CHAIN_V6" -j RETURN
}
fw3_rebuild() { fw3_ensure_sets; reconcile_policy; fw3_rebuild_v4; fw3_rebuild_v6; }
fw3_verify() {
    local rg_first
    iptables -C INPUT -j "$FW3_CHAIN_V4" >/dev/null 2>&1 || return 1
    rg_first="$(iptables -S INPUT | awk '$1 == "-A" && $2 == "INPUT" { print; exit }')"; [ "$rg_first" = "-A INPUT -j $FW3_CHAIN_V4" ] || return 1
    if [ -s "$DEVICES_V6_FILE" ]; then
        fw3_ipv6_capable || return 1; ip6tables -C INPUT -j "$FW3_CHAIN_V6" >/dev/null 2>&1 || return 1
        rg_first="$(ip6tables -S INPUT | awk '$1 == "-A" && $2 == "INPUT" { print; exit }')"; [ "$rg_first" = "-A INPUT -j $FW3_CHAIN_V6" ] || return 1
    elif command -v ip6tables >/dev/null 2>&1 && ip6tables -C INPUT -j "$FW3_CHAIN_V6" >/dev/null 2>&1; then return 1; fi
}

fw4_flush_set() { nft flush set inet fw4 "$1" >/dev/null 2>&1 || true; }
fw4_add_lines() {
    local rg_set="$1" rg_file="$2" rg_kind="$3" rg_value
    [ -r "$rg_file" ] || return 0
    while IFS= read -r rg_value; do
        [ -n "$rg_value" ] || continue
        case "$rg_kind" in
            ifname) valid_device "$rg_value" || continue; nft -f - <<EOF2
add element inet fw4 $rg_set { "$rg_value" }
EOF2
                ;;
            port) valid_uint "$rg_value" || continue; [ "$rg_value" -ge 1 ] && [ "$rg_value" -le 65535 ] || continue; nft -f - <<EOF2
add element inet fw4 $rg_set { $rg_value }
EOF2
                ;;
        esac
    done < "$rg_file"
}
fw4_load_family() {
    local rg_family="$1" rg_record rg_records rg_ip rg_dev rg_port rg_expires rg_remaining rg_meta rg_scope rg_auth_set rg_auth_if rg_ping_if rg_auth_port rg_verify_set rg_verify_if rg_verify_port rg_source rg_mode rg_network
    if [ "$rg_family" = ipv4 ]; then rg_auth_set=weig_remote_gate_auth_ipv4; rg_auth_if=weig_remote_gate_auth_ifname_v4; rg_ping_if=weig_remote_gate_auth_ping_ifname_v4; rg_auth_port=weig_remote_gate_auth_udp_port_v4; rg_verify_set=weig_remote_gate_verify_ipv4; rg_verify_if=weig_remote_gate_verify_ifname_v4; rg_verify_port=weig_remote_gate_verify_udp_port_v4; else rg_auth_set=weig_remote_gate_auth_ipv6; rg_auth_if=weig_remote_gate_auth_ifname_v6; rg_ping_if=weig_remote_gate_auth_ping_ifname_v6; rg_auth_port=weig_remote_gate_auth_udp_port_v6; rg_verify_set=weig_remote_gate_verify_ipv6; rg_verify_if=weig_remote_gate_verify_ifname_v6; rg_verify_port=weig_remote_gate_verify_udp_port_v6; fi
    rg_record="$(read_verify_record "$rg_family" 2>/dev/null || true)"
    if [ -n "$rg_record" ]; then
        set -- $rg_record; rg_source="$1"; rg_dev="$2"; rg_port="$3"; rg_expires="$4"; rg_remaining="$5"; rg_mode="$6"
        if [ "$rg_source" = any ]; then [ "$rg_family" = ipv4 ] && rg_network=0.0.0.0/0 || rg_network=::/0; else rg_network="$rg_source"; fi
        nft -f - <<EOF2
add element inet fw4 $rg_verify_set { $rg_network timeout ${rg_remaining}s }
add element inet fw4 $rg_verify_if { "$rg_dev" }
add element inet fw4 $rg_verify_port { $rg_port }
EOF2
    fi
    rg_records="$(read_auth_records "$rg_family" 2>/dev/null || true)"
    if [ -n "$rg_records" ]; then
        printf '%s\n' "$rg_records" | while IFS= read -r rg_record; do
            [ -n "$rg_record" ] || continue
            set -- $rg_record; rg_ip="$1"; rg_dev="$2"; rg_port="$3"; rg_expires="$4"; rg_remaining="$5"; rg_meta="$6"
            nft -f - <<EOF2
add element inet fw4 $rg_auth_set { $rg_ip timeout ${rg_remaining}s }
EOF2
        done
        rg_record="$(printf '%s\n' "$rg_records" | sed -n '1p')"
        set -- $rg_record; rg_ip="$1"; rg_dev="$2"; rg_port="$3"; rg_expires="$4"; rg_remaining="$5"; rg_meta="$6"; rg_scope="${rg_meta%%:*}"
        nft -f - <<EOF2
add element inet fw4 $rg_auth_if { "$rg_dev" }
add element inet fw4 $rg_auth_port { $rg_port }
EOF2
        if [ "$rg_scope" = wg_ping ]; then nft -f - <<EOF2
add element inet fw4 $rg_ping_if { "$rg_dev" }
EOF2
        fi
    fi
}
fw4_restore_sets() {
    local rg_s
    nft list set inet fw4 weig_remote_gate_protected_ifname_v4 >/dev/null 2>&1 || return 1
    for rg_s in weig_remote_gate_protected_ifname_v4 weig_remote_gate_protected_ifname_v6 weig_remote_gate_protected_udp_port weig_remote_gate_auth_ipv4 weig_remote_gate_auth_ipv6 weig_remote_gate_auth_ifname_v4 weig_remote_gate_auth_ifname_v6 weig_remote_gate_auth_ping_ifname_v4 weig_remote_gate_auth_ping_ifname_v6 weig_remote_gate_auth_udp_port_v4 weig_remote_gate_auth_udp_port_v6 weig_remote_gate_verify_ipv4 weig_remote_gate_verify_ipv6 weig_remote_gate_verify_ifname_v4 weig_remote_gate_verify_ifname_v6 weig_remote_gate_verify_udp_port_v4 weig_remote_gate_verify_udp_port_v6; do fw4_flush_set "$rg_s"; done
    fw4_add_lines weig_remote_gate_protected_ifname_v4 "$DEVICES_V4_FILE" ifname
    fw4_add_lines weig_remote_gate_protected_ifname_v6 "$DEVICES_V6_FILE" ifname
    fw4_add_lines weig_remote_gate_protected_udp_port "$PORTS_FILE" port
    reconcile_policy
    fw4_load_family ipv4; fw4_load_family ipv6
}

restore_rules() { ensure_state; local rg_b; rg_b="$(backend)" || return 1; case "$rg_b" in fw3-iptables) fw3_rebuild ;; fw4-nftables) fw4_restore_sets ;; *) return 1 ;; esac; }

install_rules() {
    ensure_state
    local rg_b
    rg_b="$(detect_backend)" || fail "unsupported firewall: need fw4+nft or fw3+iptables+ipset"
    printf '%s\n' "$rg_b" > "$BACKEND_FILE"; chmod 600 "$BACKEND_FILE"; register_include "$rg_b"
    case "$rg_b" in
        fw4-nftables) write_fw4_includes; fw4 -q check || fail "firewall4 rendered ruleset check failed"; fw4_check_order || fail "Remote Gate fw4 rules are not before conntrack established handling"; /etc/init.d/firewall reload; restore_rules; fw4_check_order || fail "Remote Gate fw4 rule order validation failed after reload" ;;
        fw3-iptables) fw3_ensure_sets; restore_rules; fw3_verify || fail "Remote Gate fw3 INPUT guard is not first" ;;
    esac
    logger -t "$TAG" "installed firewall backend $rg_b" 2>/dev/null || true; printf '%s\n' "$rg_b"
}

normalize_list_to_file() {
    local rg_input="$1" rg_kind="$2" rg_out="$3" rg_tmp rg_value
    rg_tmp="${rg_out}.tmp.$$"; : > "$rg_tmp"
    for rg_value in $rg_input; do
        case "$rg_kind" in device) valid_device "$rg_value" || fail "invalid protected device: $rg_value" ;; port) valid_uint "$rg_value" || fail "invalid protected UDP port: $rg_value"; [ "$rg_value" -ge 1 ] && [ "$rg_value" -le 65535 ] || fail "UDP port out of range: $rg_value" ;; esac
        printf '%s\n' "$rg_value" >> "$rg_tmp"
    done
    sort -u "$rg_tmp" > "$rg_out"; rm -f "$rg_tmp"; chmod 600 "$rg_out"
}
sync_policy() {
    ensure_state
    local rg_v4 rg_v6 rg_ports
    case "$#" in 2) rg_v4="$1"; rg_v6=""; rg_ports="$2" ;; 3) rg_v4="$1"; rg_v6="$2"; rg_ports="$3" ;; *) fail "usage: $0 sync <ipv4-devices> [ipv6-devices] <wireguard-udp-ports>" ;; esac
    if [ -n "$rg_v6" ] && [ "$(backend 2>/dev/null || true)" = fw3-iptables ] && ! fw3_ipv6_capable; then fail "IPv6 Gate requested but ip6tables/ipset inet6 support is unavailable"; fi
    normalize_list_to_file "$rg_v4" device "$DEVICES_V4_FILE"; normalize_list_to_file "$rg_v6" device "$DEVICES_V6_FILE"; normalize_list_to_file "$rg_ports" port "$PORTS_FILE"; restore_rules
}
