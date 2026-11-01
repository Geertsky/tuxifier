#!/usr/bin/env bash
# SPDX-License-Identifier: EUPL-1.2
# Create the sysimage of a Rocky Linux release: the directory tree dracut runs in to build the incubator initramfs
# (kernel, dracut with the dracut-sshd module, mdadm, lvm2, cryptsetup). An existing sysimage is left alone.
#
#   sysimage.sh rocky8|rocky9|rocky10
#
# Needs root rights (sudo) for dnf --installroot. The packages come from a local mirror if it answers, else from
# dl.rockylinux.org; set ROCKY_MIRROR to choose (the tree below it is <release>/BaseOS/x86_64/os/).
set -euo pipefail
# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

distro="${1:?usage: $0 rocky8|rocky9|rocky10}"
release="$(distro_version "$distro")"
root="$SYSIMAGE_DIR/rocky$release"

if [[ -d "$root/lib/modules" ]] && [[ -n "$(sysimage_kernel_version "$root")" ]]; then
    echo "sysimage $root exists (kernel $(sysimage_kernel_version "$root"))"
    exit 0
fi

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

sshd_module="$DRACUT_SSHD/46sshd"
[[ -d "$sshd_module" ]] || { echo "dracut-sshd not found at $DRACUT_SSHD, set DRACUT_SSHD (git clone https://github.com/gsauthof/dracut-sshd)" >&2; exit 1; }

gpgkey="$REPO_DIR/roles/ansible_tuxifier/files/etc/pki/rpm-gpg/RPM-GPG-KEY-Rocky-$release"
[[ -r "$gpgkey" ]] || { echo "$gpgkey not found" >&2; exit 1; }

repodir="$(mktemp -d)"
trap 'rm -rf "$repodir"' EXIT
for repo in BaseOS AppStream; do
    cat > "$repodir/rocky-$repo.repo" <<EOF
[rocky-$repo]
name=Rocky Linux $release - $repo
baseurl=$mirror/$release/$repo/x86_64/os/
gpgcheck=1
gpgkey=file://$gpgkey
EOF
done

echo "creating the sysimage $root from $mirror"
sudo mkdir -p "$root"
sudo dnf -y --installroot="$root" --releasever="$release" --setopt=reposdir="$repodir" \
    --setopt=install_weak_deps=False --setopt=tsflags=nodocs install \
    kernel dracut dracut-network NetworkManager openssh-server mdadm lvm2 cryptsetup \
    e2fsprogs xfsprogs dosfstools iproute util-linux kmod systemd-udev rocky-release

sudo cp -a "$sshd_module" "$root/usr/lib/dracut/modules.d/46sshd"
sudo chroot "$root" ssh-keygen -A
sudo sh -c "sysimage_kernel=\$(ls '$root/lib/modules' | grep -v '+debug\$' | sort -V | tail -1); echo \"\$sysimage_kernel\" > '$root/VERSION'"
echo "sysimage $root created, kernel $(cat "$root/VERSION")"
