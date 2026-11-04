#!/usr/bin/env bash
# SPDX-License-Identifier: EUPL-1.2
# Build the incubator initramfs of a sysimage for the tests, and print the paths of the kernel and the image.
#
#   initramfs.sh SYSIMAGE      FORCE=1 rebuilds an image that is up to date
#
# SYSIMAGE is the name of a directory in SYSIMAGE_DIR, like rocky9 or rhel9. The rocky sysimages are created when they
# are missing; build the others with sysimage_build.sh. The sysimage of a distribution gives an initramfs with the
# kernel of that distribution, which is what continue_install needs.
#
# The image is $TUXIFIER_TEST_DIR/<distro>/initramfs.img. It lets the test key log in as root, whatever the
# dracut_authorized_keys of the sysimage say: the file is covered by a bind mount during the build and the
# sysimage itself is not changed. The python-nest.squashfs of the dracut-incubator checkout is used; if it is
# missing, build it first (/tuxifier:rebuild-env) or download it, see the README of dracut-incubator.
# The role needs chroot in the initramfs. dracut of EL installs it (module base), dracut of fedora does not, so it is
# added here. Needs root rights (sudo).
set -euo pipefail
# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

distro="${1:?usage: $0 SYSIMAGE}"
root="$SYSIMAGE_DIR/$distro"
module="$(realpath "$DRACUT_INCUBATOR")/94incubator"
out="$TUXIFIER_TEST_DIR/$distro"

[[ -f "$module/python-nest.squashfs" ]] || { echo "$module/python-nest.squashfs is missing, see the README of dracut-incubator" >&2; exit 1; }
if [[ "$distro" == rocky* ]]; then
    "$TESTS_SCRIPTS_DIR/sysimage.sh" "$distro" >&2
elif [[ ! -d "$root/lib/modules" ]]; then
    echo "sysimage $root is missing, build it with sysimage_build.sh (see tests/scripts/mirror-url.sh for the url)" >&2
    exit 1
fi
ensure_test_key

version="$(sysimage_kernel_version "$root")"
kernel="$root/boot/vmlinuz-$version"
[[ -r "$kernel" ]] || { echo "kernel $kernel not readable" >&2; exit 1; }
mkdir -p "$out"
image="$out/initramfs.img"

up_to_date() {
    [[ -f "$image" && -z "${FORCE:-}" ]] || return 1
    [[ "$(cat "$out/kernel-version" 2>/dev/null)" == "$version" ]] || return 1
    local newer
    newer="$(find "$module" "$TEST_KEY.pub" -newer "$image" -type f -not -name 'python-nest.squashfs.*' | head -1)"
    [[ -z "$newer" ]]
}

# Envs that run in parallel build an initramfs once.
exec 8> "$out/.lock"
flock 8
if up_to_date; then
    echo "initramfs $image is up to date" >&2
else
    echo "building $image for kernel $version" >&2
    keyfile="$(mktemp)"
    cp "$TEST_KEY.pub" "$keyfile"
    mounted=()
    cleanup() {
        local m
        for ((i = ${#mounted[@]} - 1; i >= 0; i--)); do
            m="${mounted[i]}"
            sudo umount "$m" || sudo umount -l "$m" || true
        done
        rm -f "$keyfile"
    }
    trap cleanup EXIT

    bind() { sudo mount --bind "$1" "$2" && mounted+=("$2"); }
    for m in sys dev proc; do bind "/$m" "$root/$m"; done
    sudo mkdir -p "$root/usr/lib/dracut/modules.d/94incubator" "$root/root/.ssh"
    bind "$module" "$root/usr/lib/dracut/modules.d/94incubator"
    [[ -e "$root/root/.ssh/dracut_authorized_keys" ]] || sudo touch "$root/root/.ssh/dracut_authorized_keys"
    bind "$keyfile" "$root/root/.ssh/dracut_authorized_keys"

    sudo chroot "$root" dracut -NM -a incubator -I chroot --force /tuxifier-test-initramfs.img "$version" >&2
    sudo install -o "$(id -u)" -g "$(id -g)" -m 0644 "$root/tuxifier-test-initramfs.img" "$image"
    sudo rm -f "$root/tuxifier-test-initramfs.img"
    echo "$version" > "$out/kernel-version"
    cleanup
    trap - EXIT
fi
echo "kernel=$kernel"
echo "initrd=$image"
