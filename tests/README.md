# Test environment of geertsky.tuxifier

This document describes how the tests of the collection are built and how to use, extend and repair them. The short version
is in the [README](../README.md#testing). Everything is started with [tox](https://tox.wiki); there are no GitHub Actions,
the tests run on a developer machine.

## Overview

There are three kinds of tests.

1. Static checks and unit tests: `yamllint`, `ansible-lint`, `codespell`, `markdownlint`, `shellcheck`, `flake8`, `pylint`,
   `black`, `py314` (pytest of the module), `ansible-test-sanity` and `ansible-test-units`. They are the default environments
   of `tox`.
2. Installation tests: the environments `qemu-*`. A distribution is installed with the role in a throwaway qemu VM, the VM
   boots the installed system, and the result is checked. They are not in the default list: they need KVM, sudo and a lot of
   time.
3. The same two kinds for `tuxifier-playbook` (its own `tox.ini`: linters and a syntax check). The end-to-end test of the
   playbook with libvirt VMs is the skill `/tuxifier:test-installers`, not part of tox.

The environments report what they find. Fixing findings is separate work; see `~/tmp/lint-findings.txt` (generated report) and
`.plan/FINDINGS.md` of the project.

## Layout of the repository

```text
tox.ini                      all environments and the factors of the qemu environments
tests/
  tests_install.yml          the role run (installs the distribution in the VM)
  tests_installed.yml        checks of the booted installed system
  tests_negative.yml         wrong input fails clearly and leaves the disk alone
  tests_kernel_mismatch.yml  ansible_tuxifier__continue_install with a kernel that is not in the repository
  tests_demo.yml             the demo site of tuxifier-playbook works on the installed system
  tasks/                     shared task files (run_role, verify_*, check_failure, disk_fingerprint, demo_site)
  vars/                      qemu_rocky.yml (distribution), qemu_boot_<fw>.yml, qemu_layout_<layout>.yml
  scripts/                   the shell scripts below
  unit/                      pytest tests of the module
```

The layout follows linux-system-roles.storage: thin `tests_*.yml` playbooks, shared files in `tasks/` and `vars/`. The
playbooks select the distribution, firmware and layout from environment variables with `lookup('env', ...)`, so one playbook
serves every environment. The role variables are in `vars_files`, because the chroot host of the role only sees group and
play variables.

## How an installation test runs

The VM is started with qemu direct kernel boot: the kernel and the incubator initramfs come from a sysimage (below), not
from a disk. The target is an empty qcow2 disk (`/dev/vda`, plus `/dev/vdb` and `/dev/vdc` for the RAID layouts). The network
is user mode with forwarded ports (ssh, and 80 for the demo). The console is a unix socket with a log file. UEFI uses OVMF
with a private copy of the variables file per VM.

Environment names:

```text
qemu-<distro>-<firmware>-<mode>-<layout>     the install matrix
qemu-<distro>-<firmware>-<scenario>          the scenarios
```

- `distro`: `rocky8`, `rocky9`, `rocky10`, `rhel8`, `rhel9`, `rhel10`, `almalinux9`, `almalinux10`, `fedora38`, `fedora44`.
- `firmware`: `bios` or `uefi`.
- `mode`: `poweroff` or `continue`.
- `layout`: `lvm`, `parts`, `luks`, `raid`, `raidluks`, `cryptroot`.
- `scenario`: `keys`, `selinux`, `negative`, `demo` (all distributions); `distchange`, `kernelmismatch` (rocky only).

The flow of mode `poweroff` (`ansible_tuxifier__continue_install: false`):

1. `qemu-vm.sh start`: boot the initramfs on the empty disk.
2. `tests_install.yml -e ansible_tuxifier__reinstall=true`: the role installs; the initramfs powers the VM off.
3. `qemu-vm.sh wait-poweroff`, then `restart` on the same disk.
4. `tests_install.yml -e ansible_tuxifier__reinstall=false`: the second run must change nothing.
5. `permissive-first-boot`: add `enforcing=0` to the boot entries of the disk (over nbd, needs sudo).
6. `boot-disk`: boot the installed system from the disk; `tests_installed.yml` checks mounts, logical volumes, LUKS, RAID and
   (UEFI) the boot entry.

The flow of mode `continue` (`ansible_tuxifier__continue_install: true`): the role runs, the initramfs boots on into the installed system, which
is checked; the VM is powered off from inside, restarted, the role runs a second time, and the system is checked again. This
only works when the repository of the distribution has the kernel of the initramfs, which is why each distribution has its own
sysimage.

Layouts are the files `tests/vars/qemu_layout_*.yml`. They define the install disk, the expected mounts, logical volumes,
LUKS devices and RAID arrays; the checks in `verify_installed.yml` are generic and read these lists. The encrypted root
(`cryptroot`) needs the passphrase at boot: `qemu-vm.sh` types it on the serial console (`QEMU_LUKS_PASSPHRASE`).

## Scripts (`tests/scripts`)

- `qemu-vm.sh`: the VM. Commands `start`, `restart`, `wait-poweroff`, `wait-installed`, `poweroff-installed`,
  `permissive-first-boot`, `boot-disk`, `change-vars` and `stop`. Its header lists every variable.
- `initramfs.sh SYSIMAGE`: builds `~/.cache/tuxifier-tests/<sysimage>/initramfs.img` with dracut in the sysimage and prints
  `kernel=` and `initrd=`. The test key is added without changing the sysimage. It rebuilds when the kernel, the
  dracut-incubator files or the test key are newer; `FORCE=1` forces it. A lock makes parallel environments build it once.
- `sysimage_build.sh BASEOS_URL`: builds a sysimage, see below.
- `sysimage.sh rocky8|rocky9|rocky10`: the same for Rocky, with a mirror search.
- `mirror-url.sh MIRROR DISTRO`: the BaseOS url of a distribution on the local mirror layout.
- `run-parallel.sh ENV...`: several environments at once.
- `run-tier.sh TIER`: a set of environments: `smoke` (40), `layouts` (72), `full` (332).
- `common.sh`: the directories and helper functions, sourced by the others.

## Sysimages

A sysimage is a directory tree with a kernel, dracut with the dracut-sshd module, mdadm, lvm2, cryptsetup and so on. dracut
runs in it (chroot) to build the incubator initramfs. Each distribution has one in `SYSIMAGE_DIR` (default
`~/work/tuxifier`), named like the distribution: `rocky8` to `fedora44`.

Build one from a repository, independent of the tests:

```bash
tests/scripts/sysimage_build.sh http://192.168.122.1/rhel/9.8/BaseOS/
tests/scripts/sysimage_build.sh -n fedora44 https://dl.fedoraproject.org/pub/fedora/linux/releases/44/Everything/x86_64/os/
tests/scripts/sysimage_build.sh $(tests/scripts/mirror-url.sh http://192.168.122.1 almalinux10)
```

The distribution and release come from the url; `-n`, `-r`, `-a`, `-k`, `-o` override the name, release, AppStream url, gpg key
and directory. Things to know:

- It needs sudo and the dracut-sshd checkout (`DRACUT_SSHD`, default `~/git/dracut-sshd`).
- The scriptlets of the packages are skipped (the one of `kernel-core` fails in an installroot under dnf5); the script installs
  `filesystem` with scriptlets first and runs `depmod`, `ldconfig` and the kernel copy to `/boot` itself.
- `/proc`, `/sys`, `/dev` and `/run` are mounted in the tree during the install and unmounted at the end. If a build is killed
  halfway, look for leftovers with `mount | grep work/tuxifier` before deleting a sysimage directory.
- rhel packages carry a second (ML-DSA) signature; the key for it is in `tests/scripts/keys/`.
- The local fedora mirror lacks `dracut-network`; use the official repositories for fedora.
- A sysimage counts as complete when it has `modules.dep` and `boot/vmlinuz-<version>`.

## Running tests

```bash
tox                                       # linters, unit tests, ansible-test
tox -e yamllint -- roles/                  # one tool, one path (arguments after --)
tox -e qemu-rocky9-bios-poweroff-lvm       # one installation
tests/scripts/run-tier.sh -n smoke         # list the environments of a tier
tests/scripts/run-tier.sh -m http://192.168.122.1 -j 4 smoke
tests/scripts/run-tier.sh -d rocky9,rhel9 -m http://192.168.122.1 layouts
tests/scripts/run-parallel.sh -m http://192.168.122.1 qemu-fedora44-uefi-demo qemu-rhel9-bios-keys
```

`run-parallel.sh` writes `LOGDIR/<env>.log` and `LOGDIR/<env>.result` and prints a summary. It runs 4 jobs by default (each VM
has 2 GiB and 2 CPUs), stops an environment after 40 minutes (`-t`) and exports `-m` as `QEMU_MIRROR` and as the matching
`QEMU_REPO_URL`. An environment takes about four minutes.

Repositories: without `QEMU_REPO_URL` the role uses the online mirrorlist of the distribution. A local mirror is faster and the
only option for rhel (its mirrors are not public; the demo scenario is skipped for rhel without one). The url has to work on
the machine that runs tox too, because the package list is resolved there.

## Environment variables

For the VM see the header of `qemu-vm.sh`. The most useful:

- `QEMU_REPO_URL`: baseurl of the BaseOS repository to install from.
- `QEMU_MIRROR`: base url of the local mirror (distribution change test).
- `QEMU_INITRAMFS`: sysimage to take the initramfs from (default: the one of the distribution).
- `QEMU_MEMORY` (2048), `QEMU_SCRATCH_SIZE` (8G), `QEMU_KEEP_DISK=1` (keep the disk when the environment stops).
- `SYSIMAGE_DIR` (`~/work/tuxifier`), `TUXIFIER_TEST_DIR` (`~/.cache/tuxifier-tests`: test keys and initramfs images),
  `DRACUT_INCUBATOR` (default `../dracut-incubator`, needs `94incubator/python-nest.squashfs`), `DRACUT_SSHD`.

## Requirements of the machine

KVM, `qemu-system-x86_64`, `qemu-img`, `qemu-nbd` (the nbd kernel module), OVMF in `/usr/share/OVMF`, `dnf`, `rsync`, `npx`
(for markdownlint), Python 3.14 for `py314` and `ansible-test`, and passwordless `sudo` for: dracut and dnf in a sysimage,
mounts, and `qemu-nbd` (to edit the boot entries of the target disk). Four parallel VMs need about 8 GiB of free memory.

## Adding things

- A layout: add `tests/vars/qemu_layout_<name>.yml` (copy one), add the name to the factor list in `tox.ini` and to `LAYOUTS` in
  `run-tier.sh`; set `QEMU_EXTRA_DISKS` for the new factor in `tox.ini` if it needs more disks.
- A distribution: add `roles/ansible_tuxifier/vars/<name><version>.yml`, the entry in `tests/vars/qemu_rocky.yml`
  (`__test_distros`), the url in `mirror-url.sh`, build its sysimage, and add the name to the factor and to `ALL_DISTROS`.
- A scenario: a `tests_<name>.yml`, a tox environment `qemu-{...}-{bios,uefi}-<name>` (copy `demo`), the name in `run-tier.sh`.
- A check of the installed system: a task file in `tests/tasks/` included from `tests_installed.yml`.

## Troubleshooting

- Look at the log of the environment first (`LOGDIR/<env>.log`; `run-parallel.sh` uses `${TMPDIR:-/tmp}/tuxifier-tests-logs` when
  `-l` is not given). The console of the VM is `.tox/<env>/tmp/qemu/console.log`.
- A screenshot of a hung VM: the monitor socket is `/tmp/tuxifier-tests-<md5 of the workdir>.sock` (the first 12 characters of
  `printf %s "$PWD/.tox/<env>/tmp/qemu" | md5sum`). Then, for example,
  `printf 'screendump /tmp/vm.ppm\n' | socat - UNIX-CONNECT:<socket>` and view the file (`convert /tmp/vm.ppm /tmp/vm.png`).
- A stale VM after a killed run: `pgrep -a qemu-system`, then remove it with its pid file in `.tox/<env>/tmp/qemu`. The
  `stop` command (tox `commands_post`) does it on a normal exit.
- Mounts left by a killed sysimage build: `mount | grep work/tuxifier`; make them private and detach lazily
  (`mount --make-rprivate DIR; umount -R -l DIR`), never delete the tree first.
- `ansible-galaxy` 502 or a download error in `commands_pre`: a network blip, run the environment again.
- The role fails with a signature error (NOKEY) for rhel: the repository is not the RHEL content; set `QEMU_REPO_URL`.
- `continue` fails with a missing kernel: the sysimage does not match the repository; rebuild the sysimage from the same
  repository that `QEMU_REPO_URL` points to.
- Unix socket paths are limited to 108 bytes; the scripts use short paths under `/tmp` for that reason.
