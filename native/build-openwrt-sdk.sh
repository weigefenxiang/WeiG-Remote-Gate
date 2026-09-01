#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
RESOLVER="$ROOT/resolve-abi.sh"
PACKAGE_TEMPLATE="$ROOT/openwrt-sdk-package/Makefile"
SOURCE="$ROOT/remote-gate-mapper.c"
ENTRY="$ROOT/remote-gate-mapper-entry.c"
VERSION_FILE="$ROOT/../VERSION"

usage() {
    echo "usage: $0 <sdk-root> <expected-package-abi> [output-dir]" >&2
    exit 2
}

[ "$#" -ge 2 ] && [ "$#" -le 3 ] || usage

SDK_ROOT="$1"
EXPECTED_ABI="$2"
OUT_DIR="${3:-$ROOT/dist-sdk}"
PACKAGE_DIR="$SDK_ROOT/package/weig-remote-gate-mapper"
SDK_FORCE_PREREQ="${REMOTE_GATE_SDK_FORCE_PREREQ:-0}"
SDK_ALLOW_COMPILER_PREREQ="${REMOTE_GATE_SDK_ALLOW_COMPILER_PREREQ:-0}"
SDK_LINK_FLAGS="${REMOTE_GATE_SDK_LINK_FLAGS:-}"
LEGACY_PREREQ_LOG=""

case "$EXPECTED_ABI" in ''|*[!A-Za-z0-9_.+-]*) usage ;; esac
case "$SDK_FORCE_PREREQ" in 0|1) ;; *) echo "invalid REMOTE_GATE_SDK_FORCE_PREREQ" >&2; exit 1 ;; esac
case "$SDK_ALLOW_COMPILER_PREREQ" in 0|1) ;; *) echo "invalid REMOTE_GATE_SDK_ALLOW_COMPILER_PREREQ" >&2; exit 1 ;; esac
case "$SDK_LINK_FLAGS" in
    '') ;;
    '-Wl,--build-id=sha1') ;;
    *) echo "invalid REMOTE_GATE_SDK_LINK_FLAGS" >&2; exit 1 ;;
esac
if [ "$SDK_ALLOW_COMPILER_PREREQ" = 1 ] && [ "$SDK_FORCE_PREREQ" != 1 ]; then
    echo "REMOTE_GATE_SDK_ALLOW_COMPILER_PREREQ is restricted to the legacy SDK path" >&2
    exit 1
fi
if [ -n "$SDK_LINK_FLAGS" ] && [ "$SDK_FORCE_PREREQ" != 1 ]; then
    echo "REMOTE_GATE_SDK_LINK_FLAGS is restricted to the legacy SDK path" >&2
    exit 1
fi
# Re-export only the validated value consumed by the injected package Makefile.
REMOTE_GATE_SDK_LINK_FLAGS="$SDK_LINK_FLAGS"
export REMOTE_GATE_SDK_LINK_FLAGS

[ -d "$SDK_ROOT" ] || { echo "SDK root not found: $SDK_ROOT" >&2; exit 1; }
[ -r "$SDK_ROOT/rules.mk" ] || { echo "not an OpenWrt-family SDK root: $SDK_ROOT" >&2; exit 1; }
[ -r "$PACKAGE_TEMPLATE" ] && [ -r "$SOURCE" ] && [ -r "$ENTRY" ] && [ -r "$VERSION_FILE" ] || exit 1

resolved="$(sh "$RESOLVER" full "$EXPECTED_ABI" 2>/dev/null)" || {
    echo "unsupported package ABI: $EXPECTED_ABI" >&2
    exit 1
}
class="$(printf '%s\n' "$resolved" | awk -F '\t' '{print $1}')"
delivery="$(printf '%s\n' "$resolved" | awk -F '\t' '{print $2}')"
validation="$(printf '%s\n' "$resolved" | awk -F '\t' '{print $5}')"

[ -n "$class" ] && [ -n "$delivery" ] && [ -n "$validation" ] || exit 1

version="$(sed -n '1p' "$VERSION_FILE" | tr -d '\r\n')"
case "$version" in ''|*[!0-9A-Za-z._+-]*) echo "invalid VERSION" >&2; exit 1 ;; esac

if [ -e "$PACKAGE_DIR" ]; then
    [ -f "$PACKAGE_DIR/.weig-remote-gate-owned" ] || {
        echo "refusing to replace non-Remote-Gate SDK package directory: $PACKAGE_DIR" >&2
        exit 1
    }
    rm -rf "$PACKAGE_DIR"
fi
mkdir -p "$PACKAGE_DIR/src" "$OUT_DIR"
: > "$PACKAGE_DIR/.weig-remote-gate-owned"
cp "$PACKAGE_TEMPLATE" "$PACKAGE_DIR/Makefile"
cp "$SOURCE" "$PACKAGE_DIR/src/remote-gate-mapper.c"
cp "$ENTRY" "$PACKAGE_DIR/src/remote-gate-mapper-entry.c"
printf '%s\n' "$version" > "$PACKAGE_DIR/VERSION"

cleanup() {
    if [ -f "$PACKAGE_DIR/.weig-remote-gate-owned" ]; then
        rm -rf "$PACKAGE_DIR"
    fi
    [ -z "$LEGACY_PREREQ_LOG" ] || rm -f "$LEGACY_PREREQ_LOG"
}
trap cleanup EXIT INT TERM

host_compiler_version_ok() {
    compiler="$1"
    version_text="$("$compiler" -dumpfullversion -dumpversion 2>/dev/null | sed -n '1p')" || return 1
    major="${version_text%%.*}"
    rest="${version_text#*.}"
    if [ "$rest" = "$version_text" ]; then
        minor=0
    else
        minor="${rest%%.*}"
    fi
    case "$major" in ''|*[!0-9]*) return 1 ;; esac
    case "$minor" in ''|*[!0-9]*) return 1 ;; esac
    if [ "$major" -gt 4 ] || { [ "$major" -eq 4 ] && [ "$minor" -ge 8 ]; }; then
        printf '%s=%s\n' "$compiler" "$version_text" >&2
        return 0
    fi
    return 1
}

validate_host_compiler() {
    compiler="$1"
    language="$2"
    probe="$SDK_ROOT/tmp/.remote-gate-${language}-compiler-probe"

    command -v "$compiler" >/dev/null 2>&1 || return 1
    host_compiler_version_ok "$compiler" || return 1
    rm -f "$probe"
    case "$language" in
        c)
            printf '%s\n' 'int main(void) { return 0; }' | "$compiler" -x c -o "$probe" - || return 1
            ;;
        cxx)
            printf '%s\n' 'int main() { return 0; }' | "$compiler" -x c++ -o "$probe" - -lstdc++ || return 1
            ;;
        *) return 1 ;;
    esac
    "$probe" >/dev/null 2>&1 || return 1
    rm -f "$probe"
    return 0
}

prepare_legacy_prereq_stamp() {
    prereq_mk="$SDK_ROOT/include/prereq-build.mk"
    prereq_stamp="$SDK_ROOT/staging_dir/host/.prereq-build"
    LEGACY_PREREQ_LOG="$SDK_ROOT/tmp/.remote-gate-prereq.log"

    [ -r "$prereq_mk" ] || {
        echo "legacy SDK prerequisite bypass refused: include/prereq-build.mk is missing" >&2
        return 1
    }

    mkdir -p "$SDK_ROOT/tmp" "$SDK_ROOT/staging_dir/host"
    rm -f "$SDK_ROOT/tmp/.prereq-error" "$LEGACY_PREREQ_LOG"

    set +e
    (
        cd "$SDK_ROOT"
        make TOPDIR="$SDK_ROOT/" -r -s -f "$prereq_mk" prereq
    ) >"$LEGACY_PREREQ_LOG" 2>&1
    prereq_status=$?
    set -e

    cat "$LEGACY_PREREQ_LOG"

    if [ "$prereq_status" -eq 0 ]; then
        touch "$prereq_stamp"
        return 0
    fi

    failed_checks="$(sed -n "s/^Checking '\([^']*\)'\.\.\. failed\.$/\1/p" "$LEGACY_PREREQ_LOG" | LC_ALL=C sort -u)"
    failure_messages="$(sed -n 's/^Build dependency:[[:space:]]*//p' "$LEGACY_PREREQ_LOG" | sed '/^[[:space:]]*$/d' | LC_ALL=C sort -u)"

    expected_checks="python"
    expected_messages="Please install Python 2.x"
    compiler_false_negative=0

    if printf '%s\n' "$failed_checks" | grep -Fx 'gcc' >/dev/null 2>&1; then
        [ "$SDK_ALLOW_COMPILER_PREREQ" = 1 ] || {
            echo "legacy SDK prerequisite bypass refused: gcc prerequisite failed outside validated compiler compatibility mode" >&2
            return 1
        }
        validate_host_compiler gcc c || {
            echo "legacy SDK prerequisite bypass refused: host gcc failed independent version or compile validation" >&2
            return 1
        }
        expected_checks="$(printf '%s\n%s\n' "$expected_checks" 'gcc' | LC_ALL=C sort -u)"
        expected_messages="$(printf '%s\n%s\n' "$expected_messages" 'Please install the GNU C Compiler (gcc) 4.8 or later' | LC_ALL=C sort -u)"
        compiler_false_negative=1
    fi

    if printf '%s\n' "$failed_checks" | grep -Fx 'g++' >/dev/null 2>&1; then
        [ "$SDK_ALLOW_COMPILER_PREREQ" = 1 ] || {
            echo "legacy SDK prerequisite bypass refused: g++ prerequisite failed outside validated compiler compatibility mode" >&2
            return 1
        }
        validate_host_compiler g++ cxx || {
            echo "legacy SDK prerequisite bypass refused: host g++ failed independent version or compile validation" >&2
            return 1
        }
        expected_checks="$(printf '%s\n%s\n' "$expected_checks" 'g++' | LC_ALL=C sort -u)"
        expected_messages="$(printf '%s\n%s\n' "$expected_messages" 'Please install the GNU C++ Compiler (g++) 4.8 or later' | LC_ALL=C sort -u)"
        compiler_false_negative=1
    fi

    if [ "$failed_checks" != "$expected_checks" ] || [ "$failure_messages" != "$expected_messages" ]; then
        echo "legacy SDK prerequisite bypass refused: prerequisite failures exceed validated legacy host exceptions" >&2
        return 1
    fi

    # OpenWrt 19.07's defconfig path re-enters prepare-tmpinfo, which
    # unconditionally requests this stamp even when the legacy checks are
    # obsolete on a modern host. We have executed the full official target.
    # Python 2 is not used by this self-contained C package. Some early 19.07
    # point releases also reject GCC >= 10 due to a version-regex bug; when
    # that happens we independently require gcc/g++ >= 4.8 and prove both
    # compilers can build and execute a minimal program before accepting it.
    touch "$prereq_stamp"
    if [ "$compiler_false_negative" = 1 ]; then
        echo "OpenWrt 19.07 prerequisite gate bypassed only for missing Python 2 and independently validated compiler-version false negatives." >&2
    else
        echo "OpenWrt 19.07 prerequisite gate bypassed only for missing Python 2." >&2
    fi
}

if [ "$SDK_FORCE_PREREQ" = 1 ]; then
    prepare_legacy_prereq_stamp
fi

(
    cd "$SDK_ROOT"
    make defconfig
)

[ -r "$SDK_ROOT/.config" ] || {
    echo "SDK defconfig did not create .config: $SDK_ROOT/.config" >&2
    exit 1
}

sdk_abi="$(sed -n 's/^CONFIG_TARGET_ARCH_PACKAGES="\([^"]*\)"/\1/p' "$SDK_ROOT/.config" | sed -n '1p')"
if [ -z "$sdk_abi" ]; then
    sdk_abi="$(sed -n 's/^CONFIG_TARGET_ARCH_PACKAGES=\([^[:space:]]*\)$/\1/p' "$SDK_ROOT/.config" | sed -n '1p')"
    sdk_abi="${sdk_abi#\"}"
    sdk_abi="${sdk_abi%\"}"
fi
[ -n "$sdk_abi" ] || {
    echo "SDK does not expose CONFIG_TARGET_ARCH_PACKAGES after defconfig; refusing to guess ABI" >&2
    exit 1
}
[ "$sdk_abi" = "$EXPECTED_ABI" ] || {
    echo "SDK ABI mismatch: expected $EXPECTED_ABI, SDK reports $sdk_abi" >&2
    exit 1
}

(
    cd "$SDK_ROOT"
    make package/weig-remote-gate-mapper/clean >/dev/null 2>&1 || true
    make package/weig-remote-gate-mapper/compile V=s -j1
)

# OpenWrt's autoremove phase may remove the direct build binary after the IPK
# is created. Recover the mapper from package staging when that happens.
binary=""
for candidate in \
    "$(find "$SDK_ROOT/build_dir" -type f -path "*/remote-gate-mapper-${version}/remote-gate-mapper" 2>/dev/null | sed -n '1p')" \
    "$(find "$SDK_ROOT/build_dir" -type f -path "*/remote-gate-mapper-${version}/.pkgdir/remote-gate-mapper/usr/lib/remote-gate/remote-gate-mapper" 2>/dev/null | sed -n '1p')" \
    "$(find "$SDK_ROOT/build_dir" -type f -path "*/remote-gate-mapper-${version}/ipkg-*/remote-gate-mapper/usr/lib/remote-gate/remote-gate-mapper" 2>/dev/null | sed -n '1p')"
do
    [ -n "$candidate" ] || continue
    [ -f "$candidate" ] || continue
    binary="$candidate"
    break
done
[ -n "$binary" ] || {
    echo "SDK build completed without a mapper binary" >&2
    find "$SDK_ROOT/bin" -type f -name 'remote-gate-mapper_*' -print 2>/dev/null | sed 's/^/SDK package output: /' >&2 || true
    exit 1
}
chmod 0755 "$binary" 2>/dev/null || true

out="$OUT_DIR/remote-gate-mapper-$EXPECTED_ABI"
cp "$binary" "$out"
chmod 0755 "$out"

if command -v file >/dev/null 2>&1; then
    description="$(file "$out")"
    printf '%s\n' "$description"
    printf '%s\n' "$description" | grep -qi 'statically linked' || {
        echo "SDK mapper output is not statically linked: $EXPECTED_ABI" >&2
        rm -f "$out"
        exit 1
    }
fi

sha256=""
if command -v sha256sum >/dev/null 2>&1; then
    sha256="$(sha256sum "$out" | awk '{print $1}')"
fi
printf 'package_abi=%s\n' "$EXPECTED_ABI"
printf 'build_class=%s\n' "$class"
printf 'delivery=%s\n' "$delivery"
printf 'validation=%s\n' "$validation"
printf 'sha256=%s\n' "$sha256"
printf '%s\n' "$out"
