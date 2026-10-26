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
| `geertsky.tuxifier.rpm_install` | Imports the GPG keys that are missing in the rpm keyring of a root and installs the packages that are not installed in that root, with `rpm`. Can reimport the rpm database with the `rpmdb` of the installed system. Running it again changes nothing. |

The role uses `generate_minimal_install_info` to find the packages to install, and `rpm_install` to install them. See `ansible-doc geertsky.tuxifier.generate_minimal_install_info` and `ansible-doc geertsky.tuxifier.rpm_install` for the parameters and return values.

## Requirements

* ansible-core 2.15 or newer (`requires_ansible` in [meta/runtime.yml](meta/runtime.yml)), and the collections `community.general` and `ansible.posix`. The collections are installed with this collection. A second run of the role (the one that reads the installed system) was tested with every ansible-core from 2.15 to 2.21, after a first install with 2.21.
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

Only version 9 and 10 are supported. Version 8 is not, because of its `platform-python` 3.6, its Berkeley DB rpm database and its EFI `grub.cfg`; see the [note in the role README](roles/ansible_tuxifier/README.md#supported-distributions). The `el8` branch supports version 8 only.

## Development

The unit tests need the collection to be in a directory called `ansible_collections/geertsky/tuxifier`:

```
mkdir -p /tmp/ac/ansible_collections/geertsky
ln -s "$PWD" /tmp/ac/ansible_collections/geertsky/tuxifier
cd /tmp/ac/ansible_collections/geertsky/tuxifier
PYTHONPATH=/tmp/ac python3 -m pytest tests/unit
```

Commit messages in this repository start with the area they change, for example `Scope: role|Gather the facts of the installed system and check its distribution` or `Docs: ...`.

## License

EUPL-1.2, see [LICENSE](LICENSE).
