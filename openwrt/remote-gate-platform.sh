#!/bin/sh
set -u

release_value() {
    key="$1"
    [ -r /etc/openwrt_release ] || return 1
    sed -n "s/^${key}='\([^']*\)'/\1/p" /etc/openwrt_release | sed -n '1p'
}

os_release_value() {
    key="$1"
    [ -r /etc/os-release ] || return 1
    sed -n "s/^${key}=\"\{0,1\}\([^\"]*\)\"\{0,1\}$/\1/p" /etc/os-release | sed -n '1p'
}

board_release_arch() {
    command -v ubus >/dev/null 2>&1 || return 1
    command -v jsonfilter >/dev/null 2>&1 || return 1
    board="$(ubus call system board 2>/dev/null || true)"
    [ -n "$board" ] || return 1
    printf '%s' "$board" | jsonfilter -e '@.release.arch' 2>/dev/null | sed -n '1p'
}

platform_distribution() {
    value="$(release_value DISTRIB_ID 2>/dev/null || true)"
    [ -n "$value" ] || value="$(os_release_value NAME 2>/dev/null || true)"
    [ -n "$value" ] || value=unknown
    printf '%s\n' "$value"
}

platform_release() {
    value="$(release_value DISTRIB_RELEASE 2>/dev/null || true)"
    [ -n "$value" ] || value="$(os_release_value VERSION_ID 2>/dev/null || true)"
    [ -n "$value" ] || value=unknown
    printf '%s\n' "$value"
}

platform_target() {
    value="$(release_value DISTRIB_TARGET 2>/dev/null || true)"
    [ -n "$value" ] || value=unknown
    printf '%s\n' "$value"
}

package_manager() {
    if command -v apk >/dev/null 2>&1; then
        printf '%s\n' apk
    elif command -v opkg >/dev/null 2>&1; then
        printf '%s\n' opkg
    else
        printf '%s\n' none
    fi
}

opkg_arch() {
    command -v opkg >/dev/null 2>&1 || return 1
    opkg print-architecture 2>/dev/null | awk '
        $1 == "arch" && $2 != "all" && $2 != "noarch" {
            priority = $3 + 0
            if (!found || priority >= best) {
                arch = $2
                best = priority
                found = 1
            }
        }
        END { if (found) print arch }
    '
}

package_arch() {
    value="$(board_release_arch 2>/dev/null || true)"
    if [ -n "$value" ]; then printf '%s\n' "$value"; return 0; fi

    value="$(release_value DISTRIB_ARCH 2>/dev/null || true)"
    if [ -n "$value" ]; then printf '%s\n' "$value"; return 0; fi

    if command -v apk >/dev/null 2>&1; then
        value="$(apk --print-arch 2>/dev/null | sed -n '1p')"
        if [ -n "$value" ]; then printf '%s\n' "$value"; return 0; fi
    fi

    value="$(opkg_arch 2>/dev/null || true)"
    [ -n "$value" ] || return 1
    printf '%s\n' "$value"
}

kernel_arch() {
    uname -m 2>/dev/null || printf '%s\n' unknown
}

libc_family() {
    for file in /lib/ld-musl-*.so.1 /usr/lib/ld-musl-*.so.1; do
        [ -e "$file" ] && { printf '%s\n' musl; return 0; }
    done
    for file in /lib/ld-uClibc.so.* /lib/ld-uClibc-*.so.*; do
        [ -e "$file" ] && { printf '%s\n' uclibc; return 0; }
    done
    for file in /lib/ld-linux*.so.* /lib64/ld-linux*.so.*; do
        [ -e "$file" ] && { printf '%s\n' glibc; return 0; }
    done
    printf '%s\n' unknown
}

init_system() {
    if [ -r /etc/rc.common ] && { [ -x /sbin/procd ] || command -v procd >/dev/null 2>&1; }; then
        printf '%s\n' procd
    elif [ -r /etc/rc.common ]; then
        printf '%s\n' rc.common
    else
        printf '%s\n' unknown
    fi
}

firewall_generation() {
    if command -v fw4 >/dev/null 2>&1 && command -v nft >/dev/null 2>&1; then
        printf '%s\n' fw4
    elif command -v fw3 >/dev/null 2>&1 && command -v iptables >/dev/null 2>&1 && command -v ipset >/dev/null 2>&1; then
        printf '%s\n' fw3
    else
        printf '%s\n' unsupported
    fi
}

core_runtime_capable() {
    for cmd in sh curl ubus jsonfilter awk sed grep sort uci ip; do
        command -v "$cmd" >/dev/null 2>&1 || return 1
    done
    [ -r /etc/rc.common ] || return 1
    return 0
}

mapper_abi() {
    arch="$(package_arch 2>/dev/null || true)"
    [ -n "$arch" ] || return 1
    printf '%s\n' "$arch"
}

summary() {
    arch="$(package_arch 2>/dev/null || true)"
    [ -n "$arch" ] || arch=unknown
    printf 'Distribution: %s\n' "$(platform_distribution)"
    printf 'Release: %s\n' "$(platform_release)"
    printf 'Target: %s\n' "$(platform_target)"
    printf 'Package manager: %s\n' "$(package_manager)"
    printf 'Package ABI: %s\n' "$arch"
    printf 'Kernel machine: %s\n' "$(kernel_arch)"
    printf 'libc: %s\n' "$(libc_family)"
    printf 'Init: %s\n' "$(init_system)"
    printf 'Firewall generation: %s\n' "$(firewall_generation)"
    if core_runtime_capable; then
        printf 'Core runtime: capable\n'
    else
        printf 'Core runtime: missing-required-capability\n'
    fi
}

case "${1:-summary}" in
    distribution) platform_distribution ;;
    release) platform_release ;;
    target) platform_target ;;
    package-manager) package_manager ;;
    package-arch|mapper-abi) mapper_abi ;;
    kernel-arch) kernel_arch ;;
    libc) libc_family ;;
    init) init_system ;;
    firewall) firewall_generation ;;
    core-capable) core_runtime_capable ;;
    summary) summary ;;
    *)
        echo "usage: $0 distribution|release|target|package-manager|package-arch|mapper-abi|kernel-arch|libc|init|firewall|core-capable|summary" >&2
        exit 2
        ;;
esac
