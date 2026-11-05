# SPDX-License-Identifier: EUPL-1.2
# Shared settings of the sysimage, initramfs and qemu scripts. Source it, do not run it.
#
#   SYSIMAGE_DIR       directory with the sysimages rocky8, rocky9 and rocky10 (default: ~/work/tuxifier)
#   TUXIFIER_TEST_DIR  cache of the test key and of the initramfs images built for the tests (default: ~/.cache/tuxifier-tests)
#   DRACUT_INCUBATOR   checkout of dracut-incubator (default: <repo>/../dracut-incubator)
#   DRACUT_SSHD        checkout of dracut-sshd, only needed to create a sysimage (default: ~/git/dracut-sshd)

TESTS_SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$TESTS_SCRIPTS_DIR/../.." && pwd)"
SYSIMAGE_DIR="${SYSIMAGE_DIR:-$HOME/work/tuxifier}"
TUXIFIER_TEST_DIR="${TUXIFIER_TEST_DIR:-$HOME/.cache/tuxifier-tests}"
DRACUT_INCUBATOR="${DRACUT_INCUBATOR:-$REPO_DIR/../dracut-incubator}"
DRACUT_SSHD="${DRACUT_SSHD:-$HOME/git/dracut-sshd}"
TEST_KEY="$TUXIFIER_TEST_DIR/id_ed25519"

# Rocky major version of a name like rocky9 or 9.
distro_version() {
    local v="${1#rocky}"
    case "$v" in 8|9|10) echo "$v" ;; *) echo "unsupported distribution '$1', use rocky8, rocky9 or rocky10" >&2; return 1 ;; esac
}

# The kernel the initramfs is built for: VERSION of the sysimage, else the newest non-debug kernel.
sysimage_kernel_version() {
    local dir="$1"
    if [[ -s "$dir/VERSION" ]]; then
        cat "$dir/VERSION"
    else
        find "$dir/lib/modules" -mindepth 1 -maxdepth 1 -printf '%f\n' | grep -v '+debug$' | sort -V | tail -1
    fi
}

# A second key, for the test of ansible_tuxifier__root_authorized_keys: the installed system has to accept it too.
EXTRA_KEY="$TUXIFIER_TEST_DIR/id_ed25519_extra"

ensure_test_key() {
    mkdir -p "$TUXIFIER_TEST_DIR"
    [[ -f "$TEST_KEY" ]] || ssh-keygen -q -t ed25519 -N '' -C tuxifier-tests -f "$TEST_KEY"
    [[ -f "$EXTRA_KEY" ]] || ssh-keygen -q -t ed25519 -N '' -C tuxifier-tests-extra -f "$EXTRA_KEY"
}

# The distribution that the distribution change test (tox factor distchange) installs after the one of QEMU_DISTRO.
change_target_distro() {
    case "$1" in
        rocky8) echo rhel8 ;;
        rocky9) echo almalinux9 ;;
        rocky10) echo almalinux10 ;;
        *) echo "no distribution to change to from $1" >&2; return 1 ;;
    esac
}
