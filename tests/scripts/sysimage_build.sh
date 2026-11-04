#!/usr/bin/env bash
# SPDX-License-Identifier: EUPL-1.2
# Build a sysimage from a repository: the directory tree dracut runs in to build the incubator initramfs (kernel,
# dracut with the dracut-sshd module, mdadm, lvm2, cryptsetup). Works for every distribution tuxifier knows and does
# not depend on the tests or on continue_install. An existing sysimage is left alone.
#
#   sysimage_build.sh [-n NAME] [-r RELEASEVER] [-a APPSTREAM_URL] [-k GPGKEY] [-o DIR] BASEOS_URL
#
#   sysimage_build.sh http://192.168.122.1/rhel/9.8/BaseOS/
#   sysimage_build.sh -n fedora44 https://dl.fedoraproject.org/pub/fedora/linux/releases/44/Everything/x86_64/os/
#
#   BASEOS_URL   the baseurl of the BaseOS repository (of Everything for fedora). The distribution and the release
#                are taken from the url: rocky, rhel, almalinux or fedora, and the first number in the path.
#   -n NAME      name of the sysimage and so of the directory below DIR (default: distribution + major version,
#                like rhel9)
#   -r RELEASE   the $releasever of dnf (default: the major version)
#   -a URL       the AppStream repository (default: BaseOS in the url replaced by AppStream; none for fedora)
#   -k GPGKEY    gpg key of the repository (default: the key of the role in roles/ansible_tuxifier/files; rhel also
#                gets keys/RPM-GPG-KEY-PQC-redhat-release, the ML-DSA key of the second signature on recent packages)
#   -o DIR       directory with the sysimages (default: SYSIMAGE_DIR, ~/work/tuxifier)
#
# Needs root rights (sudo) for dnf --installroot, and the dracut-sshd checkout (DRACUT_SSHD).
set -euo pipefail
# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

usage() { sed -n '5,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' >&2; exit 2; }

name="" release="" appstream="" gpgkey="" outdir="$SYSIMAGE_DIR"
while getopts n:r:a:k:o:h opt; do
    case "$opt" in
        n) name="$OPTARG" ;;
        r) release="$OPTARG" ;;
        a) appstream="$OPTARG" ;;
        k) gpgkey="$OPTARG" ;;
        o) outdir="$OPTARG" ;;
        *) usage ;;
    esac
done
shift $((OPTIND - 1))
baseos="${1:-}"
[[ -n "$baseos" && $# -eq 1 ]] || usage
baseos="${baseos%/}/"

distro="$(grep -oiE 'rocky|rhel|almalinux|fedora' <<< "$baseos" | head -1 | tr '[:upper:]' '[:lower:]' || true)"
[[ -n "$distro" ]] || { echo "cannot tell the distribution from $baseos (rocky, rhel, almalinux or fedora)" >&2; exit 1; }
version="$(grep -oE "/[0-9]+(\.[0-9]+)?/" <<< "${baseos#*://*/}" | head -1 | tr -d / || true)"
[[ -n "$version" ]] || { echo "cannot find the release number in $baseos" >&2; exit 1; }
major="${version%%.*}"
[[ -n "$name" ]] || name="$distro$major"
[[ -n "$release" ]] || release="$major"
root="$outdir/$name"

case "$distro" in
    rocky) releasepkg=rocky-release; key="RPM-GPG-KEY-Rocky-$major" ;;
    rhel) releasepkg=redhat-release; key="RPM-GPG-KEY-redhat-release" ;;
    almalinux) releasepkg=almalinux-release; key="RPM-GPG-KEY-AlmaLinux-$major" ;;
    fedora) releasepkg=fedora-release-common; key="RPM-GPG-KEY-fedora-$major-primary" ;;
esac
[[ -n "$gpgkey" ]] || gpgkey="$REPO_DIR/roles/ansible_tuxifier/files/etc/pki/rpm-gpg/$key"
[[ -r "$gpgkey" ]] || { echo "gpg key $gpgkey not found, use -k" >&2; exit 1; }
gpgkeys="file://$gpgkey"
if [[ "$distro" == rhel ]]; then
    gpgkeys+=$'\n       file://'"$TESTS_SCRIPTS_DIR/keys/RPM-GPG-KEY-PQC-redhat-release"
fi
if [[ -z "$appstream" && "$distro" != fedora && "$baseos" == */BaseOS/* ]]; then
    appstream="${baseos/\/BaseOS\//\/AppStream\/}"
fi

if [[ -d "$root/lib/modules" ]] && [[ -n "$(sysimage_kernel_version "$root")" ]] \
    && [[ -e "$root/lib/modules/$(sysimage_kernel_version "$root")/modules.dep" ]]; then
    echo "sysimage $root exists (kernel $(sysimage_kernel_version "$root"))"
    exit 0
fi

sshd_module="$DRACUT_SSHD/46sshd"
[[ -d "$sshd_module" ]] || { echo "dracut-sshd not found at $DRACUT_SSHD, set DRACUT_SSHD (git clone https://github.com/gsauthof/dracut-sshd)" >&2; exit 1; }
curl -sfI -m 10 "${baseos}repodata/repomd.xml" > /dev/null || { echo "no repository at $baseos" >&2; exit 1; }

repodir="$(mktemp -d)"
trap 'rm -rf "$repodir"' EXIT
write_repo() { # id url
    cat > "$repodir/$1.repo" <<REPO
[$1]
name=$distro $version - $1
baseurl=$2
gpgcheck=1
gpgkey=$gpgkeys
REPO
}
write_repo "$distro-BaseOS" "$baseos"
[[ -z "$appstream" ]] || write_repo "$distro-AppStream" "$appstream"

echo "creating the sysimage $root from $baseos"
sudo mkdir -p "$root/proc" "$root/sys" "$root/dev"
# the scriptlet of kernel-core runs dracut in the root, and dracut needs /proc, /sys, /dev and /run there. The binds
# are made slave so that unmounting them cannot reach the mounts of the host.
mounts=()
unmount() {
    local i
    for ((i = ${#mounts[@]} - 1; i >= 0; i--)); do
        sudo mount --make-rprivate "${mounts[i]}" 2> /dev/null || true
        sudo umount -R -l "${mounts[i]}" 2> /dev/null || true
    done
    mounts=()
}
trap 'unmount; rm -rf "$repodir"' EXIT
sudo mkdir -p "$root/run" "$root/etc"
# kernel-install in the scriptlet of kernel-core fails without a machine id
[[ -s "$root/etc/machine-id" ]] || sudo sh -c "od -An -N16 -tx1 /dev/urandom | tr -d ' \n' > '$root/etc/machine-id'; echo >> '$root/etc/machine-id'"
for m in proc sys dev; do
    sudo mount --rbind "/$m" "$root/$m"
    mounts+=("$root/$m")
    sudo mount --make-rslave "$root/$m"
done
# the sysimage does not need the initramfs that kernel-install would build in it: mask those plugins
sudo mkdir -p "$root/etc/kernel/install.d"
for plugin in 50-dracut.install 51-dracut-rescue.install; do
    sudo ln -sf /dev/null "$root/etc/kernel/install.d/$plugin"
done
sudo mount -t tmpfs tmpfs "$root/run"
mounts+=("$root/run")
sudo dnf -y --installroot="$root" --releasever="$release" --setopt=reposdir="$repodir" \
    --setopt=install_weak_deps=False --setopt=tsflags=nodocs,noscripts install \
    kernel dracut dracut-network NetworkManager openssh-server mdadm lvm2 cryptsetup \
    e2fsprogs xfsprogs dosfstools iproute util-linux kmod systemd-udev "$releasepkg"

sudo cp -a "$sshd_module" "$root/usr/lib/dracut/modules.d/46sshd"
sudo chroot "$root" ssh-keygen -A
# the scriptlets are skipped, so do their depmod and ldconfig here
kernel="$(sudo ls "$root/lib/modules" | grep -v '+debug$' | sort -V | tail -1)"
sudo chroot "$root" depmod -a "$kernel"
sudo chroot "$root" ldconfig
echo "$kernel" | sudo tee "$root/VERSION" > /dev/null
unmount
echo "sysimage $root created, kernel $(cat "$root/VERSION")"
