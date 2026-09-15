#!/bin/sh
set -u

CONFIG_FILE="/etc/remote-gate.conf"
AGENT="/usr/lib/remote-gate/remote-gate-agent.sh"
EGRESS_PROBE="/usr/lib/remote-gate/remote-gate-egress-probe.sh"
MAPPING="/usr/lib/remote-gate/remote-gate-mapping.sh"
STATE_DIR="/etc/remote-gate-state"
RUNTIME_DIR="${REMOTE_GATE_RUNTIME_DIR:-/tmp/remote-gate}"
CADENCE_BODY="$RUNTIME_DIR/cadence.json"
CONTROL_STATE_FILE="$STATE_DIR/control-path"
EGRESS_PROBE_STAMP="$RUNTIME_DIR/egress-probe-last"
DIAG_SCAN_STAMP="$RUNTIME_DIR/mapper-diag-scan-last"
DIAG_SUMMARY_STAMP="$RUNTIME_DIR/mapper-diag-summary-last"
DIAG_DIR="$RUNTIME_DIR/mapper-diagnostics"
MAPPER_RUNTIME_CONFIG_STATE="$STATE_DIR/mapper-runtime-config"
LEGACY_CRON_LINE="*/5 * * * * /usr/lib/remote-gate/remote-gate-report.sh"
TAG="remote-gate-scheduler"

[ -x "$AGENT" ] || exit 1

valid_uint() { case "$1" in ''|*[!0-9]*) return 1 ;; *) return 0 ;; esac; }

config_has() {
    grep -Eq "^${1}=" "$CONFIG_FILE" 2>/dev/null
}

append_config_default() {
    key="$1"; value="$2"; file="$3"
    grep -Eq "^${key}=" "$file" 2>/dev/null || printf "%s='%s'\n" "$key" "$value" >> "$file"
}

ensure_config_defaults() {
    [ -r "$CONFIG_FILE" ] || return 1
    need=0
    config_has AGENT_INTERVAL && need=1
    for key in AGENT_IDLE_INTERVAL AGENT_INTERACTIVE_INTERVAL AGENT_COMMAND_INTERVAL AGENT_EGRESS_PROBE_INTERVAL MAPPER_KEEPALIVE MAPPER_IDLE_TIMEOUT MAPPER_MAX_SESSIONS MAPPER_DIAGNOSTICS MAPPER_DIAGNOSTIC_SUMMARY_INTERVAL; do
        config_has "$key" || need=1
    done
    [ "$need" -eq 1 ] || return 0

    legacy="$(sed -n "s/^AGENT_INTERVAL=['\"]\{0,1\}\([0-9][0-9]*\)['\"]\{0,1\}$/\1/p" "$CONFIG_FILE" | sed -n '1p')"
    idle=1800
    if valid_uint "$legacy" && [ "$legacy" -ge 60 ]; then idle="$legacy"; fi

    mkdir -p "$RUNTIME_DIR"
    tmp="$RUNTIME_DIR/remote-gate.conf.migrate.$$"
    grep -Ev '^AGENT_INTERVAL=' "$CONFIG_FILE" > "$tmp" || true
    append_config_default AGENT_IDLE_INTERVAL "$idle" "$tmp"
    append_config_default AGENT_INTERACTIVE_INTERVAL 5 "$tmp"
    append_config_default AGENT_COMMAND_INTERVAL 5 "$tmp"
    append_config_default AGENT_EGRESS_PROBE_INTERVAL 1800 "$tmp"
    append_config_default MAPPER_KEEPALIVE 60 "$tmp"
    append_config_default MAPPER_IDLE_TIMEOUT 180 "$tmp"
    append_config_default MAPPER_MAX_SESSIONS 64 "$tmp"
    append_config_default MAPPER_DIAGNOSTICS 1 "$tmp"
    append_config_default MAPPER_DIAGNOSTIC_SUMMARY_INTERVAL 1800 "$tmp"
    chmod 600 "$tmp"
    mv -f "$tmp" "$CONFIG_FILE"
    logger -t "$TAG" "migrated cadence defaults: idle=${idle}s interactive=5s command=5s mapper_keepalive=60s" 2>/dev/null || true
}

cleanup_legacy_cron() {
    crontab=/etc/crontabs/root
    [ -f "$crontab" ] || return 0
    grep -Fqx "$LEGACY_CRON_LINE" "$crontab" 2>/dev/null || return 0
    mkdir -p "$RUNTIME_DIR"
    tmp="$RUNTIME_DIR/root.cron.$$"
    grep -Fvx "$LEGACY_CRON_LINE" "$crontab" > "$tmp" || true
    chmod 600 "$tmp" 2>/dev/null || true
    mv -f "$tmp" "$crontab"
    if [ -x /etc/init.d/cron ]; then /etc/init.d/cron restart >/dev/null 2>&1 || true; fi
    logger -t "$TAG" "removed legacy 5-minute Remote Gate report cron" 2>/dev/null || true
}

load_runtime_config() {
    # shellcheck disable=SC1090
    . "$CONFIG_FILE"
    AGENT_IDLE_INTERVAL="${AGENT_IDLE_INTERVAL:-1800}"
    AGENT_INTERACTIVE_INTERVAL="${AGENT_INTERACTIVE_INTERVAL:-5}"
    AGENT_COMMAND_INTERVAL="${AGENT_COMMAND_INTERVAL:-5}"
    AGENT_EGRESS_PROBE_INTERVAL="${AGENT_EGRESS_PROBE_INTERVAL:-1800}"
    MAPPER_KEEPALIVE="${MAPPER_KEEPALIVE:-60}"
    MAPPER_IDLE_TIMEOUT="${MAPPER_IDLE_TIMEOUT:-180}"
    MAPPER_MAX_SESSIONS="${MAPPER_MAX_SESSIONS:-64}"
    MAPPER_DIAGNOSTICS="${MAPPER_DIAGNOSTICS:-1}"
    MAPPER_DIAGNOSTIC_SUMMARY_INTERVAL="${MAPPER_DIAGNOSTIC_SUMMARY_INTERVAL:-1800}"

    valid_uint "$AGENT_IDLE_INTERVAL" && [ "$AGENT_IDLE_INTERVAL" -ge 60 ] || AGENT_IDLE_INTERVAL=1800
    valid_uint "$AGENT_INTERACTIVE_INTERVAL" && [ "$AGENT_INTERACTIVE_INTERVAL" -ge 5 ] && [ "$AGENT_INTERACTIVE_INTERVAL" -le 300 ] || AGENT_INTERACTIVE_INTERVAL=5
    valid_uint "$AGENT_COMMAND_INTERVAL" && [ "$AGENT_COMMAND_INTERVAL" -ge 5 ] && [ "$AGENT_COMMAND_INTERVAL" -le 300 ] || AGENT_COMMAND_INTERVAL=5
    valid_uint "$AGENT_EGRESS_PROBE_INTERVAL" && [ "$AGENT_EGRESS_PROBE_INTERVAL" -ge 60 ] || AGENT_EGRESS_PROBE_INTERVAL=1800
    valid_uint "$MAPPER_KEEPALIVE" && [ "$MAPPER_KEEPALIVE" -ge 5 ] && [ "$MAPPER_KEEPALIVE" -le 120 ] || MAPPER_KEEPALIVE=60
    valid_uint "$MAPPER_IDLE_TIMEOUT" && [ "$MAPPER_IDLE_TIMEOUT" -ge 30 ] && [ "$MAPPER_IDLE_TIMEOUT" -le 3600 ] || MAPPER_IDLE_TIMEOUT=180
    valid_uint "$MAPPER_MAX_SESSIONS" && [ "$MAPPER_MAX_SESSIONS" -ge 1 ] && [ "$MAPPER_MAX_SESSIONS" -le 256 ] || MAPPER_MAX_SESSIONS=64
    case "$MAPPER_DIAGNOSTICS" in 0|1) ;; *) MAPPER_DIAGNOSTICS=1 ;; esac
    valid_uint "$MAPPER_DIAGNOSTIC_SUMMARY_INTERVAL" && [ "$MAPPER_DIAGNOSTIC_SUMMARY_INTERVAL" -ge 60 ] || MAPPER_DIAGNOSTIC_SUMMARY_INTERVAL=1800
}

maybe_egress_probe() {
    [ -x "$EGRESS_PROBE" ] || return 0
    now="$(date +%s)"
    last="$(cat "$EGRESS_PROBE_STAMP" 2>/dev/null || echo 0)"
    valid_uint "$last" || last=0
    [ "$((now - last))" -ge "$AGENT_EGRESS_PROBE_INTERVAL" ] || return 0
    printf '%s\n' "$now" > "$EGRESS_PROBE_STAMP"
    "$EGRESS_PROBE" >/dev/null 2>&1 || true
}

control_curl() {
    output="$1"; url="$2"
    family=""; dev=""
    if [ -r "$CONTROL_STATE_FILE" ]; then
        family="$(sed -n '1p' "$CONTROL_STATE_FILE")"
        dev="$(sed -n '2p' "$CONTROL_STATE_FILE")"
    fi

    if [ -n "$dev" ] && { [ "$family" = ipv4 ] || [ "$family" = ipv6 ]; }; then
        flag=-4; [ "$family" = ipv6 ] && flag=-6
        CADENCE_CODE="$(curl "$flag" --interface "$dev" -sS --connect-timeout 6 --max-time 15 -o "$output" -w '%{http_code}' "$url" -H "Authorization: Bearer ${WRITE_TOKEN}" 2>/dev/null)" || CADENCE_CODE=000
        [ "$CADENCE_CODE" != 000 ] && return 0
    fi

    CADENCE_CODE="$(curl -sS --connect-timeout 6 --max-time 15 -o "$output" -w '%{http_code}' "$url" -H "Authorization: Bearer ${WRITE_TOKEN}" 2>/dev/null)" || CADENCE_CODE=000
    [ "$CADENCE_CODE" != 000 ]
}

cadence_mode() {
    mkdir -p "$RUNTIME_DIR"
    if ! control_curl "$CADENCE_BODY" "https://${HOSTNAME}/api/v1/agent/cadence"; then
        printf 'legacy\n'
        return 1
    fi
    [ "$CADENCE_CODE" = 200 ] || { printf 'legacy\n'; return 1; }
    mode="$(jsonfilter -i "$CADENCE_BODY" -e '@.mode' 2>/dev/null | sed -n '1p')"
    case "$mode" in idle|interactive|command) printf '%s\n' "$mode"; return 0 ;; esac
    printf 'legacy\n'
    return 1
}

maybe_restart_mapper_for_config() {
    [ -x "$MAPPING" ] || return 0
    desired="${MAPPER_KEEPALIVE}|${MAPPER_IDLE_TIMEOUT}|${MAPPER_MAX_SESSIONS}"
    current="$(sed -n '1p' "$MAPPER_RUNTIME_CONFIG_STATE" 2>/dev/null || true)"
    [ "$current" = "$desired" ] && return 0
    "$MAPPING" stop-all >/dev/null 2>&1 || true
    printf '%s\n' "$desired" > "$MAPPER_RUNTIME_CONFIG_STATE"
    chmod 600 "$MAPPER_RUNTIME_CONFIG_STATE" 2>/dev/null || true
    logger -t "$TAG" "mapper runtime configuration changed; managed mappings will be recreated" 2>/dev/null || true
}

mapper_diagnostic_tick() {
    [ "$MAPPER_DIAGNOSTICS" = 1 ] || return 0
    now="$(date +%s)"
    last_scan="$(cat "$DIAG_SCAN_STAMP" 2>/dev/null || echo 0)"
    valid_uint "$last_scan" || last_scan=0
    scan_interval="$MAPPER_KEEPALIVE"
    [ "$scan_interval" -ge 30 ] || scan_interval=30
    [ "$((now - last_scan))" -ge "$scan_interval" ] || return 0

    mkdir -p "$DIAG_DIR"
    printf '%s\n' "$now" > "$DIAG_SCAN_STAMP"
    last_summary="$(cat "$DIAG_SUMMARY_STAMP" 2>/dev/null || echo 0)"
    valid_uint "$last_summary" || last_summary=0
    summary=0
    if [ "$((now - last_summary))" -ge "$MAPPER_DIAGNOSTIC_SUMMARY_INTERVAL" ]; then
        summary=1
        printf '%s\n' "$now" > "$DIAG_SUMMARY_STAMP"
    fi

    found=0
    for status in "$RUNTIME_DIR"/mapping/*.status.json; do
        [ -f "$status" ] || continue
        found=1
        key="$(basename "$status" .status.json)"
        state="$(jsonfilter -i "$status" -e '@.state' 2>/dev/null | sed -n '1p')"
        external_address="$(jsonfilter -i "$status" -e '@.external_address' 2>/dev/null | sed -n '1p')"
        external_port="$(jsonfilter -i "$status" -e '@.external_port' 2>/dev/null | sed -n '1p')"
        observed_at="$(jsonfilter -i "$status" -e '@.observed_at' 2>/dev/null | sed -n '1p')"
        pid="$(jsonfilter -i "$status" -e '@.pid' 2>/dev/null | sed -n '1p')"
        valid_uint "$observed_at" || observed_at=0
        age=0
        [ "$observed_at" -gt 0 ] && age=$((now - observed_at))
        [ "$age" -lt 0 ] && age=0
        endpoint="${external_address}:${external_port}"
        dstate="$DIAG_DIR/$key.state"
        previous="$(sed -n '1p' "$dstate" 2>/dev/null || true)"
        changes="$(sed -n '2p' "$dstate" 2>/dev/null || echo 0)"
        valid_uint "$changes" || changes=0
        first_seen="$(sed -n '3p' "$dstate" 2>/dev/null || echo "$now")"
        valid_uint "$first_seen" || first_seen="$now"
        if [ -n "$previous" ] && [ "$previous" != ":" ] && [ "$endpoint" != ":" ] && [ "$previous" != "$endpoint" ]; then
            changes=$((changes + 1))
            logger -t remote-gate-mapper "mapping-change key=$key old=$previous new=$endpoint keepalive=${MAPPER_KEEPALIVE}s changes=$changes" 2>/dev/null || true
        fi
        { printf '%s\n' "$endpoint"; printf '%s\n' "$changes"; printf '%s\n' "$first_seen"; } > "$dstate"

        if [ "$summary" -eq 1 ]; then
            stale=0
            [ "$observed_at" -gt 0 ] && [ "$age" -gt "$((MAPPER_KEEPALIVE * 2 + 10))" ] && stale=1
            logger -t remote-gate-mapper "summary key=$key state=${state:-unknown} pid=${pid:-0} keepalive=${MAPPER_KEEPALIVE}s endpoint=${endpoint} last_stun_age=${age}s stale=$stale mapping_changes=$changes observed_window=$((now - first_seen))s" 2>/dev/null || true
        fi
    done
    if [ "$summary" -eq 1 ] && [ "$found" -eq 0 ]; then
        logger -t remote-gate-mapper "summary state=idle keepalive=${MAPPER_KEEPALIVE}s mappings=0" 2>/dev/null || true
    fi
}

report_once() {
    [ -r "$CONFIG_FILE" ] || exit 1
    load_runtime_config
    maybe_egress_probe
    "$AGENT" report
}

scheduler_loop() {
    mkdir -p "$RUNTIME_DIR" "$DIAG_DIR" "$STATE_DIR"
    ensure_config_defaults || exit 1
    cleanup_legacy_cron
    load_runtime_config
    maybe_restart_mapper_for_config
    logger -t "$TAG" "started idle=${AGENT_IDLE_INTERVAL}s interactive=${AGENT_INTERACTIVE_INTERVAL}s command=${AGENT_COMMAND_INTERVAL}s mapper_keepalive=${MAPPER_KEEPALIVE}s" 2>/dev/null || true

    last_agent_run=0
    while :; do
        load_runtime_config
        maybe_restart_mapper_for_config
        maybe_egress_probe
        now="$(date +%s)"
        mode="$(cadence_mode 2>/dev/null || true)"
        case "$mode" in
            command)
                "$AGENT" once || true
                last_agent_run="$(date +%s)"
                ;;
            interactive)
                if [ "$last_agent_run" -eq 0 ] || [ "$((now - last_agent_run))" -ge "$AGENT_INTERACTIVE_INTERVAL" ]; then
                    "$AGENT" report || true
                    last_agent_run="$(date +%s)"
                fi
                ;;
            idle)
                if [ "$last_agent_run" -eq 0 ] || [ "$((now - last_agent_run))" -ge "$AGENT_IDLE_INTERVAL" ]; then
                    "$AGENT" report || true
                    last_agent_run="$(date +%s)"
                fi
                ;;
            *)
                # Rolling-upgrade compatibility: if the VPS does not yet expose
                # cadence hints, retain the historical responsive Agent cycle.
                "$AGENT" once || true
                last_agent_run="$(date +%s)"
                ;;
        esac

        mapper_diagnostic_tick
        if [ "$mode" = legacy ] || [ -z "$mode" ]; then
            next=10
        else
            next="$AGENT_COMMAND_INTERVAL"
            [ "$AGENT_INTERACTIVE_INTERVAL" -lt "$next" ] && next="$AGENT_INTERACTIVE_INTERVAL"
        fi
        valid_uint "$next" || next=5
        [ "$next" -ge 5 ] || next=5
        sleep "$next"
    done
}

case "${1:-report}" in
    loop) scheduler_loop ;;
    report) report_once ;;
    *) echo "usage: $0 [report|loop]" >&2; exit 2 ;;
esac
