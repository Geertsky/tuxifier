#!/usr/bin/env bash
# SPDX-License-Identifier: EUPL-1.2
# Print the baseurl of the local mirror for a distribution, for QEMU_REPO_URL.
#
#   mirror-url.sh MIRROR DISTRO      MIRROR is the base url, like http://192.168.122.1; DISTRO like rocky9 or rhel8
#
# The layout of the mirror: rocky and rhel below /<name>/, the others below /mirror/<name>/, and the rhel releases
# are the minor releases of the media (8.10, 9.8, 10.2).
set -euo pipefail
mirror="${1:?usage: $0 MIRROR DISTRO}"
distro="${2:?usage: $0 MIRROR DISTRO}"
name="${distro//[0-9]/}"
version="${distro//[^0-9]/}"
case "$name" in
    rocky) echo "$mirror/rocky/$version/BaseOS/x86_64/os/" ;;
    almalinux) echo "$mirror/mirror/almalinux/$version/BaseOS/x86_64/os/" ;;
    fedora) echo "$mirror/mirror/fedora/$version/Everything/x86_64/os/" ;;
    rhel)
        case "$version" in
            8) echo "$mirror/rhel/8.10/BaseOS/" ;;
            9) echo "$mirror/rhel/9.8/BaseOS/" ;;
            10) echo "$mirror/rhel/10.2/BaseOS/" ;;
            *) echo "no mirror for $distro" >&2; exit 1 ;;
        esac ;;
    *) echo "unknown distribution $distro" >&2; exit 1 ;;
esac
