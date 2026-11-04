#!/usr/bin/env bash
# SPDX-License-Identifier: EUPL-1.2
# Run a tier of the qemu tox envs in parallel, with run-parallel.sh.
#
#   run-tier.sh [-n] [-d DISTROS] [-j JOBS] [-l LOGDIR] [-t MINUTES] [-m MIRROR] TIER
#
# TIER:
#   smoke    every distribution x bios/uefi x the layout lvm x poweroff/continue                  (40 envs)
#   layouts  rocky8, rocky9, rocky10 x every layout x bios/uefi x poweroff/continue                (72 envs)
#   full     the install matrix of every distribution x every layout x bios/uefi x poweroff/continue, and the scenarios
#            keys, selinux, negative and demo on every distribution, distchange and kernelmismatch on rocky8, rocky9 and
#            rocky10, each on bios and uefi                                                       (332 envs, hours)
#
# continue_install=true needs the kernel of the initramfs in the repository of the distribution (see kernelmismatch). The
# initramfs comes from the sysimage of the distribution, so every distribution needs its sysimage in SYSIMAGE_DIR
# (rocky ones are created, build the others with sysimage_build.sh and the url of mirror-url.sh).
#
# -n           only print the envs, one per line, and check that tox knows them
# -d DISTROS   only these distributions, comma separated, like rocky9,rhel9
# The other options are the ones of run-parallel.sh. An env takes about 4 minutes and 2 GiB of memory.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ALL_DISTROS=(rocky8 rocky9 rocky10 rhel8 rhel9 rhel10 almalinux9 almalinux10 fedora38 fedora44)
ROCKY=(rocky8 rocky9 rocky10)
FIRMWARES=(bios uefi)
MODES=(poweroff continue)
LAYOUTS=(lvm parts luks raid raidluks cryptroot)

LIST_ONLY=
DISTROS=("${ALL_DISTROS[@]}")
PASS=()
while getopts "nd:j:l:t:m:" opt; do
    case "$opt" in
        n) LIST_ONLY=1 ;;
        d) IFS=, read -r -a DISTROS <<< "$OPTARG" ;;
        j | l | t | m) PASS+=("-$opt" "$OPTARG") ;;
        *) sed -n '3,17p' "${BASH_SOURCE[0]}" >&2; exit 2 ;;
    esac
done
shift $((OPTIND - 1))
TIER="${1:?usage: $0 [-n] [-d DISTROS] [-j JOBS] [-l LOGDIR] [-t MINUTES] [-m MIRROR] smoke|layouts|full}"

# Keeps the distributions of the first list that are in the second.
only_selected() {
    local d s
    for d in "$@"; do
        for s in "${DISTROS[@]}"; do [[ "$d" == "$s" ]] && echo "$d"; done
    done
}

matrix() { # distros layouts
    local -a distros layouts
    read -r -a distros <<< "$1"
    read -r -a layouts <<< "$2"
    local d f m l
    for d in "${distros[@]}"; do
        for f in "${FIRMWARES[@]}"; do
            for m in "${MODES[@]}"; do
                for l in "${layouts[@]}"; do echo "qemu-$d-$f-$m-$l"; done
            done
        done
    done
}

scenarios() { # scenario distros
    local -a distros
    read -r -a distros <<< "$2"
    local d f
    for d in "${distros[@]}"; do
        for f in "${FIRMWARES[@]}"; do echo "qemu-$d-$f-$1"; done
    done
}

mapfile -t selected_all < <(only_selected "${ALL_DISTROS[@]}")
mapfile -t selected_rocky < <(only_selected "${ROCKY[@]}")

case "$TIER" in
    smoke) envs="$(matrix "${selected_all[*]}" lvm)" ;;
    layouts) envs="$(matrix "${selected_rocky[*]}" "${LAYOUTS[*]}")" ;;
    full)
        envs="$(matrix "${selected_all[*]}" "${LAYOUTS[*]}")"
        for s in keys selinux negative demo; do envs+=$'\n'"$(scenarios "$s" "${selected_all[*]}")"; done
        for s in distchange kernelmismatch; do envs+=$'\n'"$(scenarios "$s" "${selected_rocky[*]}")"; done
        ;;
    *) echo "unknown tier '$TIER', use smoke, layouts or full" >&2; exit 2 ;;
esac
envs="$(printf '%s\n' "$envs" | sed '/^$/d' | awk '!seen[$0]++')"
[[ -n "$envs" ]] || { echo "no envs: check -d" >&2; exit 2; }

if [[ -n "$LIST_ONLY" ]]; then
    printf '%s\n' "$envs"
    known="$(tox -a 2> /dev/null)"
    missing="$(comm -23 <(printf '%s\n' "$envs" | sort) <(printf '%s\n' "$known" | sort))"
    [[ -z "$missing" ]] || { echo "tox does not know these envs:" >&2; echo "$missing" >&2; exit 1; }
    exit 0
fi

mapfile -t env_list <<< "$envs"
exec "$SCRIPT_DIR/run-parallel.sh" "${PASS[@]}" "${env_list[@]}"
