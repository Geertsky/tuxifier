#!/usr/bin/env bash
# SPDX-License-Identifier: EUPL-1.2
# Create the sysimage of a Rocky Linux release for the tests; a wrapper around sysimage_build.sh that picks the
# mirror. An existing sysimage is left alone.
#
#   sysimage.sh rocky8|rocky9|rocky10
#
# The packages come from a local mirror if it answers, else from dl.rockylinux.org; set ROCKY_MIRROR to choose
# (the tree below it is <release>/BaseOS/x86_64/os/).
set -euo pipefail
# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

distro="${1:?usage: $0 rocky8|rocky9|rocky10}"
release="$(distro_version "$distro")"

mirror="${ROCKY_MIRROR:-}"
if [[ -z "$mirror" ]]; then
    for candidate in http://192.168.122.1/rocky https://dl.rockylinux.org/pub/rocky; do
        if curl -sfI -m 5 "$candidate/$release/BaseOS/x86_64/os/repodata/repomd.xml" > /dev/null; then
            mirror="$candidate"
            break
        fi
    done
fi
[[ -n "$mirror" ]] || { echo "no Rocky mirror answers, set ROCKY_MIRROR" >&2; exit 1; }

exec "$TESTS_SCRIPTS_DIR/sysimage_build.sh" -n "rocky$release" "$mirror/$release/BaseOS/x86_64/os/"
