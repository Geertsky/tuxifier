#!/usr/bin/env bash
# SPDX-License-Identifier: EUPL-1.2
# Run several qemu tox envs in parallel, one log per env, and print a summary.
#
#   run-parallel.sh [-j JOBS] [-l LOGDIR] [-t MINUTES] [-m MIRROR] ENV...
#
# -m MIRROR   install from the local mirror at this base url, like http://192.168.122.1 (see mirror-url.sh), unless
#              QEMU_REPO_URL is set; without -m and QEMU_REPO_URL the online mirrors of the role are used.
# ENV is a tox env, like qemu-rocky9-uefi-poweroff. Every VM takes 2 GiB of memory (QEMU_MEMORY) and 2 CPUs; the
# default of 4 jobs needs about 8 GiB of free memory. The environment (QEMU_REPO_URL and so on) is passed on to tox.
set -uo pipefail
JOBS=4
MIRROR=
TIMEOUT=40 # minutes per env; a stalled download of a mirror would otherwise hang the run for ever
LOGDIR="${TMPDIR:-/tmp}/tuxifier-tests-logs"
while getopts "j:l:t:m:" opt; do
    case "$opt" in
        j) JOBS="$OPTARG" ;;
        l) LOGDIR="$OPTARG" ;;
        t) TIMEOUT="$OPTARG" ;;
        m) MIRROR="$OPTARG" ;;
        *) echo "usage: $0 [-j JOBS] [-l LOGDIR] [-t MINUTES] [-m MIRROR] ENV..." >&2; exit 2 ;;
    esac
done
shift $((OPTIND - 1))
[[ $# -gt 0 ]] || { echo "usage: $0 [-j JOBS] [-l LOGDIR] [-t MINUTES] [-m MIRROR] ENV..." >&2; exit 2; }
mkdir -p "$LOGDIR"
rm -f "$LOGDIR"/*.result

run_env() {
    local env="$1" log distro
    log="$LOGDIR/$env.log"
    [[ -z "$MIRROR" ]] || export QEMU_MIRROR="$MIRROR"
    if [[ -n "$MIRROR" && -z "${QEMU_REPO_URL:-}" ]]; then
        distro="${env#qemu-}"
        QEMU_REPO_URL="$("$SCRIPT_DIR/mirror-url.sh" "$MIRROR" "${distro%%-*}")" || return 1
        export QEMU_REPO_URL
    fi
    if timeout --signal=INT --kill-after=2m "${TIMEOUT}m" tox -e "$env" > "$log" 2>&1; then
        echo "OK" > "$LOGDIR/$env.result"
    else
        echo "FAIL" > "$LOGDIR/$env.result"
    fi
}
export -f run_env
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export LOGDIR TIMEOUT MIRROR SCRIPT_DIR

printf '%s\n' "$@" | xargs -P "$JOBS" -I{} bash -c 'run_env {}'

status=0
for env in "$@"; do
    result="$(cat "$LOGDIR/$env.result" 2> /dev/null || echo MISSING)"
    printf '%-45s %s\n' "$env" "$result"
    [[ "$result" == OK ]] || status=1
done
exit "$status"
