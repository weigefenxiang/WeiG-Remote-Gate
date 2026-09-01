# Sourced by remote-gate-firewall.sh.
wireguard_for_port() {
    local rg_port="$1" rg_iface rg_found="" rg_count=0 rg_listen
    command -v wg >/dev/null 2>&1 || return 1
    for rg_iface in $(wg show interfaces 2>/dev/null); do
        rg_listen="$(wg show "$rg_iface" listen-port 2>/dev/null | sed -n '1p')"
        [ "$rg_listen" = "$rg_port" ] || continue
        rg_found="$rg_iface"; rg_count=$((rg_count + 1))
    done
    [ "$rg_count" -eq 1 ] || return 1
    printf '%s\n' "$rg_found"
}

wg_snapshot() {
    local rg_iface="$1" rg_out="$2"
    wg show "$rg_iface" dump 2>/dev/null | awk 'NR > 1 { print $1 "|" $3 "|" ($5+0) "|" ($6+0) }' > "$rg_out"
}

wg_endpoint_ip() {
    local rg_endpoint="$1" rg_family="$2" rg_ip
    case "$rg_endpoint" in
        \[*\]:*) rg_ip="${rg_endpoint#\[}"; rg_ip="${rg_ip%%\]*}" ;;
        *:*) rg_ip="${rg_endpoint%:*}" ;;
        *) return 1 ;;
    esac
    case "$rg_family" in ipv4) valid_ipv4 "$rg_ip" ;; ipv6) valid_ipv6 "$rg_ip" ;; *) return 1 ;; esac || return 1
    printf '%s\n' "$rg_ip"
}

wg_activity_candidates() {
    local rg_iface="$1" rg_family="$2" rg_base="$3" rg_current="$4" rg_peer rg_endpoint rg_hs rg_rx rg_old_hs rg_old_rx rg_ip
    wg_snapshot "$rg_iface" "$rg_current" || return 1
    while IFS='|' read -r rg_peer rg_endpoint rg_hs rg_rx; do
        [ -n "$rg_peer" ] || continue
        rg_ip="$(wg_endpoint_ip "$rg_endpoint" "$rg_family" 2>/dev/null || true)"; [ -n "$rg_ip" ] || continue
        rg_old_hs="$(awk -F'|' -v p="$rg_peer" '$1==p {print $3; exit}' "$rg_base" 2>/dev/null)"; rg_old_rx="$(awk -F'|' -v p="$rg_peer" '$1==p {print $4; exit}' "$rg_base" 2>/dev/null)"
        [ -n "$rg_old_hs" ] || rg_old_hs=0; [ -n "$rg_old_rx" ] || rg_old_rx=0
        if [ "$rg_hs" -gt "$rg_old_hs" ] || [ "$rg_rx" -gt "$rg_old_rx" ]; then printf '%s|%s|%s|%s\n' "$rg_peer" "$rg_ip" "$rg_hs" "$rg_rx"; fi
    done < "$rg_current"
}

wg_endpoint_hints() {
    local rg_iface="$1" rg_family="$2" rg_base="$3" rg_current="$4" rg_peer rg_endpoint rg_hs rg_rx rg_old_endpoint rg_ip
    wg_snapshot "$rg_iface" "$rg_current" || return 1
    while IFS='|' read -r rg_peer rg_endpoint rg_hs rg_rx; do
        [ -n "$rg_peer" ] || continue
        rg_ip="$(wg_endpoint_ip "$rg_endpoint" "$rg_family" 2>/dev/null || true)"; [ -n "$rg_ip" ] || continue
        rg_old_endpoint="$(awk -F'|' -v p="$rg_peer" '$1==p {print $2; exit}' "$rg_base" 2>/dev/null)"
        if [ -z "$rg_old_endpoint" ] || [ "$rg_endpoint" != "$rg_old_endpoint" ]; then printf '%s|%s\n' "$rg_peer" "$rg_ip"; fi
    done < "$rg_current"
}

unique_ip_from_lines() {
    awk -F'|' 'NF >= 2 && $2 != "" { seen[$2]=1 } END { n=0; for (x in seen) { value=x; n++ } if (n==1) print value; else if (n>1) print "AMBIGUOUS" }'
}

verification_route_set() {
    local rg_family="$1" rg_source="$2" rg_device="$3" rg_port="$4" rg_seconds="$5" rg_expires
    [ -x "$RETURN_HELPER" ] || return 0
    rg_expires="$(( $(date +%s) + rg_seconds + 3 ))"
    "$RETURN_HELPER" return-route-verify-set "$rg_family" "$rg_source" "$rg_device" "$rg_port" "$rg_expires" >/dev/null 2>&1 || true
}
verification_route_clear() {
    local rg_family="$1"
    [ -x "$RETURN_HELPER" ] || return 0
    "$RETURN_HELPER" return-route-verify-clear "$rg_family" >/dev/null 2>&1 || true
}

wait_verified_activity() {
    local rg_iface="$1" rg_family="$2" rg_base="$3" rg_expected="$4" rg_seconds="$5" rg_allow_hints="$6" rg_device="$7" rg_port="$8" rg_deadline rg_now rg_current rg_lines rg_count rg_ip rg_hints
    rg_current="${rg_base}.current"; rg_deadline="$(( $(date +%s) + rg_seconds ))"
    while :; do
        rg_lines="$(wg_activity_candidates "$rg_iface" "$rg_family" "$rg_base" "$rg_current" 2>/dev/null || true)"
        rg_count="$(printf '%s\n' "$rg_lines" | sed '/^$/d' | wc -l | tr -d ' ')"
        if [ "$rg_count" -gt 1 ]; then rm -f "$rg_current"; return 3; fi
        if [ "$rg_count" -eq 1 ]; then
            rg_ip="$(printf '%s\n' "$rg_lines" | awk -F'|' 'NR==1 {print $2}')"
            if [ -z "$rg_expected" ] || [ "$rg_ip" = "$rg_expected" ]; then printf '%s\n' "$rg_ip"; rm -f "$rg_current"; return 0; fi
        fi
        if [ "$rg_allow_hints" = yes ]; then
            rg_hints="$(wg_endpoint_hints "$rg_iface" "$rg_family" "$rg_base" "$rg_current" 2>/dev/null || true)"
            rg_ip="$(printf '%s\n' "$rg_hints" | unique_ip_from_lines)"
            if [ -z "$rg_ip" ]; then
                rg_ip="$(wg_snapshot "$rg_iface" "$rg_current" 2>/dev/null; awk -F'|' -v fam="$rg_family" '
                    function ip(ep, x) { if (ep ~ /^\[/) { sub(/^\[/,"",ep); sub(/\].*$/,"",ep); return ep } x=ep; sub(/:[0-9]+$/,"",x); return x }
                    { x=ip($2); if ((fam=="ipv4" && x ~ /^[0-9.]+$/) || (fam=="ipv6" && x ~ /:/)) print $1 "|" x }
                ' "$rg_current" 2>/dev/null | unique_ip_from_lines)"
            fi
            [ "$rg_ip" = AMBIGUOUS ] || { [ -z "$rg_ip" ] || verification_route_set "$rg_family" "$rg_ip" "$rg_device" "$rg_port" 5; }
        fi
        rg_now="$(date +%s)"; [ "$rg_now" -lt "$rg_deadline" ] || break
        sleep 1
    done
    rm -f "$rg_current"; return 1
}

verify_wireguard_source() {
    local rg_candidate="$1" rg_family="$2" rg_device="$3" rg_port="$4" rg_iface rg_base rg_actual rg_rc
    rg_iface="$(wireguard_for_port "$rg_port" 2>/dev/null || true)"; [ -n "$rg_iface" ] || return 4
    rg_base="/tmp/remote-gate-wg-verify.$$.$rg_family"; wg_snapshot "$rg_iface" "$rg_base" || { rm -f "$rg_base"; return 4; }

    verify_open "$rg_candidate" "$rg_family" "$rg_device" "$rg_port" "$VERIFY_CANDIDATE_SECONDS" candidate
    verification_route_set "$rg_family" "$rg_candidate" "$rg_device" "$rg_port" "$VERIFY_CANDIDATE_SECONDS"
    if rg_actual="$(wait_verified_activity "$rg_iface" "$rg_family" "$rg_base" "$rg_candidate" "$VERIFY_CANDIDATE_SECONDS" no "$rg_device" "$rg_port")"; then rg_rc=0; else rg_rc=$?; fi
    verify_clear "$rg_family" >/dev/null 2>&1 || true; verification_route_clear "$rg_family"
    if [ "$rg_rc" -eq 0 ] && [ -n "$rg_actual" ]; then printf '%s\n' "$rg_actual"; rm -f "$rg_base"; return 0; fi
    [ "$rg_rc" -ne 3 ] || { rm -f "$rg_base"; return 3; }

    verify_open any "$rg_family" "$rg_device" "$rg_port" "$VERIFY_DISCOVERY_SECONDS" discovery
    if rg_actual="$(wait_verified_activity "$rg_iface" "$rg_family" "$rg_base" "" "$VERIFY_DISCOVERY_SECONDS" yes "$rg_device" "$rg_port")"; then rg_rc=0; else rg_rc=$?; fi
    verify_clear "$rg_family" >/dev/null 2>&1 || true; verification_route_clear "$rg_family"; rm -f "$rg_base"
    [ "$rg_rc" -eq 0 ] && [ -n "$rg_actual" ] || return "$rg_rc"
    printf '%s\n' "$rg_actual"
}

activate() {
    local rg_source="$1" rg_family="$2" rg_scope="$3" rg_device="$4" rg_port="$5" rg_ttl="$6" rg_kind="${7:-web_verified}" rg_device_file rg_now rg_expires rg_file rg_existing rg_existing_dev rg_existing_port rg_existing_meta rg_existing_scope
    ensure_state
    valid_family "$rg_family" || fail "invalid IP family"; valid_scope "$rg_scope" || fail "invalid access scope"; valid_source_kind "$rg_kind" || fail "invalid source kind"
    if [ "$rg_family" = ipv4 ]; then valid_ipv4 "$rg_source" || fail "invalid IPv4"; else valid_ipv6 "$rg_source" || fail "invalid IPv6"; [ "$(backend 2>/dev/null || true)" != fw3-iptables ] || fw3_ipv6_capable || fail "IPv6 Gate unavailable"; fi
    valid_device "$rg_device" || fail "invalid WAN device"; valid_port "$rg_port" || fail "invalid UDP ingress port"; valid_ttl "$rg_ttl" || fail "TTL must be 1m/5m/15m/30m or 30m steps up to 12h"
    ip link show "$rg_device" >/dev/null 2>&1 || fail "WAN device does not exist: $rg_device"
    rg_device_file="$(family_device_file "$rg_family")"
    grep -Fqx "$rg_device" "$rg_device_file" 2>/dev/null || fail "WAN device is not in the protected $rg_family policy: $rg_device"
    protected_ingress_current "$rg_family" "$rg_device" "$rg_port" || fail "UDP ingress is not a locally registered Remote Gate endpoint: $rg_device/$rg_port"

    reconcile_family "$rg_family"
    rg_existing="$(read_auth_record "$rg_family" 2>/dev/null || true)"
    if [ -n "$rg_existing" ]; then
        set -- $rg_existing
        rg_existing_dev="$2"; rg_existing_port="$3"; rg_existing_meta="$6"; rg_existing_scope="${rg_existing_meta%%:*}"
        [ "$rg_existing_dev" = "$rg_device" ] && [ "$rg_existing_port" = "$rg_port" ] && [ "$rg_existing_scope" = "$rg_scope" ] || fail "authorization profile conflict; close existing access before switching WAN, ingress, or scope"
    fi

    rg_now="$(date +%s)"; rg_expires="$((rg_now + rg_ttl))"; rg_file="$(auth_record_file "$rg_family" "$rg_source")"
    { printf '%s\n' "$rg_source"; printf '%s\n' "$rg_device"; printf '%s\n' "$rg_port"; printf '%s\n' "$rg_expires"; printf '%s\n' "$rg_family"; printf '%s\n' "$rg_scope"; printf '%s\n' "$rg_kind"; } > "$rg_file"
    chmod 600 "$rg_file"
    restore_rules
    logger -t "$TAG" "$rg_family/$rg_scope web authorization active on $rg_device UDP/$rg_port for $rg_source (${rg_ttl}s, $rg_kind)" 2>/dev/null || true
}

verify_open() {
    local rg_source="$1" rg_family="$2" rg_device="$3" rg_port="$4" rg_seconds="$5" rg_mode="$6" rg_device_file rg_now rg_expires rg_file
    valid_family "$rg_family" || fail "invalid verification family"; case "$rg_mode" in candidate|discovery) ;; *) fail "invalid verification mode" ;; esac
    if [ "$rg_source" != any ]; then case "$rg_family" in ipv4) valid_ipv4 "$rg_source" ;; ipv6) valid_ipv6 "$rg_source" ;; esac || fail "invalid verification source"; fi
    [ "$rg_mode" = discovery ] || [ "$rg_source" != any ] || fail "candidate verification needs a source"
    valid_device "$rg_device" || fail "invalid WAN device"; valid_port "$rg_port" || fail "invalid UDP port"; valid_uint "$rg_seconds" || fail "invalid verification TTL"; [ "$rg_seconds" -ge 2 ] && [ "$rg_seconds" -le 30 ] || fail "verification TTL must be 2-30 seconds"
    rg_device_file="$(family_device_file "$rg_family")"; grep -Fqx "$rg_device" "$rg_device_file" 2>/dev/null || fail "verification WAN is not protected"; grep -Fqx "$rg_port" "$PORTS_FILE" 2>/dev/null || fail "verification UDP port is not WireGuard"
    rg_now="$(date +%s)"; rg_expires="$((rg_now + rg_seconds))"; rg_file="$(family_verify_file "$rg_family")"
    { printf '%s\n' "$rg_source"; printf '%s\n' "$rg_device"; printf '%s\n' "$rg_port"; printf '%s\n' "$rg_expires"; printf '%s\n' "$rg_family"; printf '%s\n' "$rg_mode"; } > "$rg_file"; chmod 600 "$rg_file"; restore_rules
}
verify_clear() { local rg_family="$1" rg_file; valid_family "$rg_family" || fail "invalid verification family"; rg_file="$(family_verify_file "$rg_family")"; rm -f "$rg_file"; restore_rules; }

clear_auth() {
    local rg_family="${1:-all}" rg_b rg_dir
    case "$rg_family" in
        ipv4|ipv6) rg_dir="$(family_auth_dir "$rg_family")"; rm -f "$rg_dir"/* "$(family_auth_file "$rg_family")" 2>/dev/null || true ;;
        all|'') rm -f "$AUTH_DIR_V4"/* "$AUTH_DIR_V6"/* "$AUTH_FILE_V4" "$AUTH_FILE_V6" 2>/dev/null || true ;;
        *) fail "invalid clear family" ;;
    esac
    rg_b="$(backend 2>/dev/null || true)"; case "$rg_b" in fw3-iptables) fw3_rebuild ;; fw4-nftables) fw4_restore_sets ;; esac
    logger -t "$TAG" "temporary authorization cleared ($rg_family)" 2>/dev/null || true
}

ready_state() { local rg_b; rg_b="$(backend 2>/dev/null || true)"; case "$rg_b" in fw3-iptables) fw3_verify >/dev/null 2>&1 ;; fw4-nftables) nft list set inet fw4 weig_remote_gate_protected_ifname_v4 >/dev/null 2>&1 && fw4_check_order >/dev/null 2>&1 ;; *) return 1 ;; esac; }

kernel_auth_active() {
    local rg_b="$1" rg_family="$2" rg_ip="$3"
    case "$rg_b:$rg_family" in
        fw3-iptables:ipv4) ipset test "$FW3_AUTH_SET_V4" "$rg_ip" >/dev/null 2>&1 ;;
        fw3-iptables:ipv6) ipset test "$FW3_AUTH_SET_V6" "$rg_ip" >/dev/null 2>&1 ;;
        fw4-nftables:ipv4) nft list set inet fw4 weig_remote_gate_auth_ipv4 2>/dev/null | grep -Fq "$rg_ip" ;;
        fw4-nftables:ipv6) nft list set inet fw4 weig_remote_gate_auth_ipv6 2>/dev/null | grep -Fq "$rg_ip" ;;
        *) return 1 ;;
    esac
}

family_status_json() {
    local rg_family="$1" rg_b="$2" rg_records rg_record rg_ip rg_dev rg_port rg_expires rg_remaining rg_meta rg_scope rg_kind rg_active=false rg_count=0 rg_sources="" rg_entries="" rg_first_ip="" rg_first_dev="" rg_first_port=0 rg_first_scope="" rg_first_kind="" rg_min=0 rg_file
    reconcile_family "$rg_family"
    rg_records="$(read_auth_records "$rg_family" 2>/dev/null || true)"
    if [ -n "$rg_records" ]; then
        while IFS= read -r rg_record; do
            [ -n "$rg_record" ] || continue
            set -- $rg_record; rg_ip="$1"; rg_dev="$2"; rg_port="$3"; rg_expires="$4"; rg_remaining="$5"; rg_meta="$6"; rg_scope="${rg_meta%%:*}"; rg_kind="${rg_meta#*:}"
            if ! kernel_auth_active "$rg_b" "$rg_family" "$rg_ip"; then
                rg_file="$(auth_record_file "$rg_family" "$rg_ip")"; rm -f "$rg_file"
                continue
            fi
            rg_active=true; rg_count=$((rg_count + 1))
            [ -n "$rg_sources" ] && rg_sources="$rg_sources,"
            rg_sources="${rg_sources}\"${rg_ip}\""
            [ -n "$rg_entries" ] && rg_entries="$rg_entries,"
            rg_entries="${rg_entries}{\"source_ip\":\"${rg_ip}\",\"source_kind\":\"${rg_kind}\",\"expires_in\":${rg_remaining}}"
            if [ -z "$rg_first_ip" ]; then
                rg_first_ip="$rg_ip"; rg_first_dev="$rg_dev"; rg_first_port="$rg_port"; rg_first_scope="$rg_scope"; rg_first_kind="$rg_kind"; rg_min="$rg_remaining"
            elif [ "$rg_remaining" -lt "$rg_min" ]; then
                rg_min="$rg_remaining"
            fi
        done <<EOF2
$rg_records
EOF2
    fi
    printf '{"active":%s,"family":"%s","scope":"%s","source_ip":"%s","source_kind":"%s","device":"%s","ingress_port":%s,"wg_port":%s,"expires_in":%s,"source_count":%s,"authorized_sources":[%s],"authorizations":[%s]}' "$rg_active" "$rg_family" "$rg_first_scope" "$rg_first_ip" "$rg_first_kind" "$rg_first_dev" "$rg_first_port" "$rg_first_port" "$rg_min" "$rg_count" "$rg_sources" "$rg_entries"
}

status_json() {
    ensure_state
    local rg_b rg_ready=false rg_ipv6=false rg_pv4 rg_pv6 rg_pp rg_pm rg_v4 rg_v6 rg_any=false rg_top_family rg_top_scope rg_top_ip rg_top_dev rg_top_port rg_top_exp rg_record rg_meta
    rg_b="$(backend 2>/dev/null || printf unsupported)"; ready_state && rg_ready=true; case "$rg_b" in fw3-iptables) fw3_ipv6_capable && rg_ipv6=true ;; fw4-nftables) rg_ipv6=true ;; esac
    rg_pv4="$(awk 'END{print NR+0}' "$DEVICES_V4_FILE" 2>/dev/null)"; rg_pv6="$(awk 'END{print NR+0}' "$DEVICES_V6_FILE" 2>/dev/null)"; rg_pp="$(awk 'END{print NR+0}' "$PORTS_FILE" 2>/dev/null)"; rg_pm="$(awk 'END{print NR+0}' "$MAPPED_INGRESS_V4_FILE" 2>/dev/null)"
    reconcile_policy; rg_v4="$(family_status_json ipv4 "$rg_b")"; rg_v6="$(family_status_json ipv6 "$rg_b")"
    printf '%s' "$rg_v4" | grep -q '"active":true' && rg_any=true; printf '%s' "$rg_v6" | grep -q '"active":true' && rg_any=true
    rg_top_family=""; rg_top_scope=""; rg_top_ip=""; rg_top_dev=""; rg_top_port=0; rg_top_exp=0
    if printf '%s' "$rg_v4" | grep -q '"active":true'; then rg_top_family=ipv4; elif printf '%s' "$rg_v6" | grep -q '"active":true'; then rg_top_family=ipv6; fi
    if [ -n "$rg_top_family" ]; then
        rg_record="$(read_auth_record "$rg_top_family" 2>/dev/null || true)"; set -- $rg_record; rg_top_ip="${1:-}"; rg_top_dev="${2:-}"; rg_top_port="${3:-0}"; rg_top_exp="${5:-0}"; rg_meta="${6:-:}"; rg_top_scope="${rg_meta%%:*}"
    fi
    printf '{"backend":"%s","ready":%s,"ipv6_capable":%s,"active":%s,"family":"%s","scope":"%s","source_ip":"%s","device":"%s","ingress_port":%s,"wg_port":%s,"expires_in":%s,"families":{"ipv4":%s,"ipv6":%s},"protected_devices_v4":%s,"protected_devices_v6":%s,"protected_ports":%s,"protected_mapped_ingress_v4":%s}\n' "$rg_b" "$rg_ready" "$rg_ipv6" "$rg_any" "$rg_top_family" "$rg_top_scope" "$rg_top_ip" "$rg_top_dev" "$rg_top_port" "$rg_top_port" "$rg_top_exp" "$rg_v4" "$rg_v6" "$rg_pv4" "$rg_pv6" "$rg_pp" "$rg_pm"
}

uninstall_rules() {
    local rg_b
    rg_b="$(backend 2>/dev/null || true)"; unregister_include
    case "$rg_b" in
        fw3-iptables) fw3_remove_jump_v4; fw3_remove_jump_v6; iptables -F "$FW3_CHAIN_V4" >/dev/null 2>&1 || true; iptables -X "$FW3_CHAIN_V4" >/dev/null 2>&1 || true; if command -v ip6tables >/dev/null 2>&1; then ip6tables -F "$FW3_CHAIN_V6" >/dev/null 2>&1 || true; ip6tables -X "$FW3_CHAIN_V6" >/dev/null 2>&1 || true; fi; ipset destroy "$FW3_AUTH_SET_V4" >/dev/null 2>&1 || true; ipset destroy "$FW3_AUTH_SET_V6" >/dev/null 2>&1 || true; ipset destroy "$FW3_VERIFY_SET_V4" >/dev/null 2>&1 || true; ipset destroy "$FW3_VERIFY_SET_V6" >/dev/null 2>&1 || true ;;
        fw4-nftables) rm -f "$FW4_TABLE_INCLUDE" "$FW4_INPUT_INCLUDE"; fw4 -q check >/dev/null 2>&1 || fail "firewall4 check failed after removing Remote Gate includes"; /etc/init.d/firewall reload ;;
    esac
    rm -f "$BACKEND_FILE" "$LEGACY_AUTH_FILE" "$AUTH_FILE_V4" "$AUTH_FILE_V6" "$VERIFY_FILE_V4" "$VERIFY_FILE_V6" "$DEVICES_V4_FILE" "$DEVICES_V6_FILE" "$LEGACY_DEVICES_FILE" "$PORTS_FILE" "$MAPPED_INGRESS_V4_FILE"
    rm -rf "$AUTH_DIR_V4" "$AUTH_DIR_V6"
    logger -t "$TAG" "firewall integration removed; original firewall behavior restored" 2>/dev/null || true
}
