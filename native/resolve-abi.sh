#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
MAP="${REMOTE_GATE_MAPPER_ABI_MAP:-$ROOT/mapper-abi-map.tsv}"
CLASSES="${REMOTE_GATE_MAPPER_BUILD_CLASSES:-$ROOT/mapper-build-classes.tsv}"

valid_key() {
    case "$1" in ''|*[!A-Za-z0-9_.+-]*) return 1 ;; *) return 0 ;; esac
}

resolve_abi() {
    abi="$1"
    valid_key "$abi" || return 1
    awk -F '\t' -v wanted="$abi" '
        $0 !~ /^#/ && NF >= 3 && $1 == wanted {
            print $2 "\t" $3
            found = 1
            exit
        }
        END { if (!found) exit 1 }
    ' "$MAP"
}

resolve_class() {
    class="$1"
    valid_key "$class" || return 1
    awk -F '\t' -v wanted="$class" '
        $0 !~ /^#/ && NF >= 4 && $1 == wanted {
            print $2 "\t" $3 "\t" $4
            found = 1
            exit
        }
        END { if (!found) exit 1 }
    ' "$CLASSES"
}

case "${1:-}" in
    abi)
        [ "$#" -eq 2 ] || exit 2
        resolve_abi "$2"
        ;;
    class)
        [ "$#" -eq 2 ] || exit 2
        resolve_class "$2"
        ;;
    full)
        [ "$#" -eq 2 ] || exit 2
        result="$(resolve_abi "$2")" || exit 1
        class="$(printf '%s\n' "$result" | awk -F '\t' '{print $1}')"
        status="$(printf '%s\n' "$result" | awk -F '\t' '{print $2}')"
        class_result="$(resolve_class "$class")" || exit 1
        printf '%s\t%s\t%s\n' "$class" "$status" "$class_result"
        ;;
    *)
        echo "usage: $0 abi <package-abi>|class <build-class>|full <package-abi>" >&2
        exit 2
        ;;
esac
