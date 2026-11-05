# Ansible Collection - geertsky.tuxifier

Partition the disks and install a minimal operating system on a bare-metal server from an initramfs built with [dracut-incubator](https://github.com/Geertsky/dracut-incubator), and then power off or continue the boot of the installed system.

## Where this fits

This repository is one of four that make up the tuxifier installer:

| Repository | Role |
|---|---|
| [dracut-incubator](https://github.com/Geertsky/dracut-incubator) | The dracut module that puts the packed python-nest environment in an initramfs and holds the boot until the install is done |
| [python-nest](https://github.com/Geertsky/python-nest) | The conda recipes and the environment that make up the python-nest environment |
| `tuxifier` (this one) | The ansible collection that runs inside that initramfs and installs the OS |
| [tuxifier-playbook](https://github.com/Geertsky/tuxifier-playbook) | An example playbook and inventory |

The machine to install is booted with the initramfs. Ansible connects to it over ssh and runs the role in the initramfs, not in an installed OS.

## Content

### Role

| Role | Description |
|------|-------------|
| [`geertsky.tuxifier.ansible_tuxifier`](roles/ansible_tuxifier/README.md) | Creates the storage layout described by `installdisk` (partitions, LVM, LUKS and md RAID) with the [linux-system-roles.storage](https://github.com/linux-system-roles/storage) role, installs the distribution described by `installdistribution` into it, sets the root password, ssh keys and boot loader, and then powers off or continues the boot. Running it again changes nothing. |

The variables, the supported distributions and the behaviour of each option are described in the [role README](roles/ansible_tuxifier/README.md).

### Modules

| Module | Description |
|--------|-------------|
| `geertsky.tuxifier.generate_minimal_install_info` | Resolves the packages and package groups of the `minimalpackages` of a distribution, with their dependencies, against its repository. Returns `packages`, a list of dicts with the `name` and the `url` of every package, `rpm_urls` with the same URLs as one string, and `package_count`. |

The role uses `generate_minimal_install_info` to find the packages to install, and installs them with the `rpm` of the python-nest environment, see the README of the role. See `ansible-doc geertsky.tuxifier.generate_minimal_install_info` for the parameters and return values.

## Requirements

* ansible-core 2.15 or newer (`requires_ansible` in [meta/runtime.yml](meta/runtime.yml)), and the collections `community.general` and `ansible.posix`. The collections are installed with this collection.
* The role [linux-system-roles.storage](https://github.com/linux-system-roles/storage), from its `main` branch. It is a role and not a collection, so it is installed separately, see below.
* The Python `dnf` module (`python3-dnf`) for `/usr/bin/python3` on the Ansible controller: `generate_minimal_install_info` is delegated to `localhost`, so the controller has to be an RPM based distribution.
* The machine to install has to boot an initramfs built with [dracut-incubator](https://github.com/Geertsky/dracut-incubator).

## Installation

```
ansible-galaxy collection install git+https://github.com/Geertsky/tuxifier.git
ansible-galaxy role install -r requirements.yml
```

The second command needs the `requirements.yml` of this repository, so run it from a checkout, or save that file first. The version of the storage role matters, see the [role README](roles/ansible_tuxifier/README.md#roles).

## Example

The host_vars of a machine with one disk, installed with Rocky Linux 9 on a BIOS machine:

```
installdistribution:
  name: rocky
  version: "9"

rootpw: rootpw        # keep this in an Ansible Vault
strict_selinux: true  # relabel the installed system at its first boot
storage_disklabel_type: gpt
installdisk_boot_disk: /dev/vda   # there is no /boot volume to take the boot disk from
installdisk:
  - name: /dev/vda
    type: partition
    disks: [/dev/vda]
    volumes:
      - name: "1"
        size: 1MiB
        fs_type: biosboot
      - name: "2"
        size: "0"     # the rest of the disk
        fs_type: ext4
        fs_label: root    # the initramfs is booted with root=LABEL=root
        fs_create_options: "-O ^orphan_file"
        mount_point: /
```

and the playbook runs the role on the machine that has booted the initramfs:

```
- name: Tuxifier
  hosts: installer
  gather_facts: false
  tasks:
    - name: Import role tuxifier
      ansible.builtin.import_role:
        name: geertsky.tuxifier.ansible_tuxifier
      environment:
        PATH: "/local/conda/envs/python-nest/sbin:/local/conda/envs/python-nest/bin:{{ ansible_facts['env']['PATH'] | default('/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin') }}"
        CONDA_PREFIX: "/local/conda/envs/python-nest"
```

The `environment` puts the python-nest environment of the initramfs, with `wipefs`, `lvm`, `blivet` and the other tools the role needs, in the `PATH`.

The [tuxifier-playbook repository](https://github.com/Geertsky/tuxifier-playbook) has the complete playbook, host_vars for every supported distribution, and the steps to build and boot the initramfs. For a quick-start please see its README.

## Supported distributions

Rocky Linux, AlmaLinux, RHEL and Fedora, see [Supported distributions](roles/ansible_tuxifier/README.md#supported-distributions) in the role README for the versions and how far each of them is tested.

Every version in the table is installed in the BIOS and UEFI test VMs, see [Testing](#testing). Version 8 differs in its `platform-python` 3.6, its Berkeley DB rpm database and its EFI `grub.cfg`; see the [note in the role README](roles/ansible_tuxifier/README.md#supported-distributions).

## Development

Commit messages in this repository start with the area they change, for example `Scope: role|Gather the facts of the installed system and check its distribution` or `Docs: ...`.

## Testing

The tests are run with [tox](https://tox.wiki). It has no plugins; the settings are in `tox.ini`, the tools are installed by tox itself. The complete description of the test environment (scripts, sysimages, flows, variables, how to extend and repair it) is in [tests/README.md](tests/README.md).

### Linters, unit tests and ansible-test

`tox` without arguments runs the default environments: `yamllint`, `ansible-lint`, `codespell`, `markdownlint`, `shellcheck`, `flake8`, `pylint`, `black`, `py314` (pytest of the module, `tests/unit`), `ansible-test-sanity` and `ansible-test-units`. The ansible-test environments copy the repository to `ansible_collections/geertsky/tuxifier` in a temporary directory, because ansible-test needs that path. They run with the ansible-core that tox installs; set `ANSIBLE_TEST_PYTHON` for another Python.

The environments report what they find; they do not fix it. The findings that exist are listed in `.plan/FINDINGS.md` of the tuxifier_project superproject, and most are not fixed yet.

### Installing in a virtual machine

The role is tested by installing a distribution in a throwaway qemu VM that boots the initramfs of dracut-incubator. The environments are called

```
qemu-<distro>-<firmware>-<mode>-<layout>
```

- `<distro>`: `rocky8`, `rocky9`, `rocky10`, `rhel8`, `rhel9`, `rhel10`, `almalinux9`, `almalinux10`, `fedora38` or `fedora44`: the distribution that is installed.
- `<firmware>`: `bios` or `uefi` (OVMF).
- `<mode>`: `poweroff` runs the role with `continue_install: false`: the VM powers off, is started again for the second run (idempotence), and the installed system is booted from its disk and checked. `continue` runs it with `continue_install: true`: the initramfs boots on into the installed system, which is checked, powered off and started again for the second run.
- `<layout>`: the storage of the install target, a file `tests/vars/qemu_layout_<layout>.yml`: `lvm`, `parts` (no LVM), `luks` (an encrypted logical volume), `raid` (a volume group on md RAID1 of two extra disks), `raidluks` and `cryptroot` (an encrypted root; the passphrase is typed at the serial console).

Other scenarios are named `qemu-<distro>-<firmware>-<scenario>`:

- `keys`: `root_authorized_keys` and `rootpw`, with a login with the second key.
- `selinux`: `strict_selinux` false and true on the same disk.
- `distchange`: one distribution installed over another on the same disk (rocky only).
- `negative`: calls with wrong input fail with a clear message and leave the disk as it was.
- `kernelmismatch`: `continue_install` with a kernel that is not in the repository (rocky only).
- `demo`: the demo site of tuxifier-playbook (httpd, the page and the firewall) is set up on the booted installed system and the page is fetched through a forwarded port. rhel needs a mirror (`QEMU_REPO_URL`) for this, else it is skipped.

The initramfs comes from the sysimage of the distribution that is installed (`QEMU_INITRAMFS` selects another one), because the mode `continue` needs the kernel of the initramfs in the repository of that distribution. The sysimages `rocky8` to `fedora44` are directories in `SYSIMAGE_DIR` (default `~/work/tuxifier`). The Rocky ones are created when missing; build the others with `tests/scripts/sysimage_build.sh`, for example `sysimage_build.sh $(tests/scripts/mirror-url.sh http://192.168.122.1 rhel9)`. It works for every distribution and does not depend on the tests.

Requirements: KVM, `qemu-img`, `qemu-nbd`, OVMF (`/usr/share/OVMF`), `sudo` (dracut and dnf in the sysimage, and `enforcing=0` in the boot entries of the install target over nbd) and the dracut-incubator checkout with `94incubator/python-nest.squashfs`. The directories and the repository are set with environment variables, for example `SYSIMAGE_DIR`, `DRACUT_INCUBATOR`, `DRACUT_SSHD`, `TUXIFIER_TEST_DIR`, `QEMU_REPO_URL`, `QEMU_MIRROR` and `QEMU_MEMORY`; [tests/README.md](tests/README.md) has the full description.

Without `QEMU_REPO_URL` the repositories of the role are used. For RHEL a mirror is required, as RHEL mirrors are not public. The package list is resolved on the machine that runs tox, so the URL has to work there and in the VM. `tests/scripts/mirror-url.sh` maps a distribution to the layout of a local mirror.

### Running many environments

`tests/scripts/run-parallel.sh ENV...` runs environments in parallel (4 by default, 2 GiB of memory each), with a log per environment and a time limit of 40 minutes. `tests/scripts/run-tier.sh` runs a set of them:

- `smoke`: every distribution on `bios` and `uefi` with the layout `lvm`.
- `layouts`: the Rocky distributions with every layout.
- `full`: the install matrix of every distribution and layout, and all scenarios.

`run-tier.sh -n TIER` only lists the environments, `-d rocky9,rhel9` limits the distributions and `-m http://192.168.122.1` uses a local mirror. An environment takes about four minutes, `smoke` about 30 minutes and `full` hours. Runs of different environments can overlap: the scripts lock the nbd device, the choice of the forwarded port and the build of the initramfs.

## License

EUPL-1.2, see [LICENSE](LICENSE).
