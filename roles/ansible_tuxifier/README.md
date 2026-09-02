# ansible-tuxifier

```
Role belongs to geertsky/tuxifier
Namespace - geertsky
Collection - tuxifier
Version - 1.0.0
Repository - http://github.com/geertsky/tuxifier
```

Description: Partition and install a server from the initramfs built with dracut-tuxifier

## Dependencies

### Initramfs image generation
For using `tuxifier`, the machine has to be booted using an initramfs image with the [dracut-tuxifier](https://github.com/geertsky/dracut-tuxifier) module included.
See: the [dracut-tuxifier](https://github.com/Geertsky/dracut-tuxifier) git repository for the steps to create the initramfs.

## Role Variables
### host_vars

| Variable                                         | Type | Description                                                                                                                                                                                   |
|--------------------------------------------------|------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `installdisk`                                    | dict | Dict to describe the install target                                                                                                                                                           |
| `installdisk.disks`                              | list | List of dicts describing the disks for the install target                                                                                                                                     |
| `installdisk.disks[0]`                           | dict | Dictionary describing one installation disk.                                                                                                                                                  |
| `installdisk.disks[0].device`                    | str  | The full-path to the block device.                                                                                                                                                            |
| `installdisk.disks[0].label`                     | str  | Disk label type supported by parted                                                                                                                                                           |
| `installdisk.disks[0].partitions`                | list | list of dictionaries describing the partitions on this disk                                                                                                                                   |
| `installdisk.disks[0].partitions[0].id`          | str  | Unique partition identifier across all disks. Used to resolve entries in `installdisk.lvm_layout[].pvs`, as the default GPT partition name, and to identify special partitions such as `efi`. |
| `installdisk.disks[0].partitions[0].number`      | int  | argument to the same named parameter of the [community.general.parted](https://docs.ansible.com/projects/ansible/latest/collections/community/general/parted_module.html) module              |
| `installdisk.disks[0].partitions[0].part_start`  | str  | argument to the same named parameter of the [community.general.parted](https://docs.ansible.com/projects/ansible/latest/collections/community/general/parted_module.html) module              |
| `installdisk.disks[0].partitions[0].part_end`    | str  | argument to the same named parameter of the [community.general.parted](https://docs.ansible.com/projects/ansible/latest/collections/community/general/parted_module.html) module              |
| `installdisk.disks[0].partitions[0].fstype`      | str  | argument to the same named parameter of the [community.general.filesystem](https://docs.ansible.com/projects/ansible/latest/collections/community/general/filesystem_module.html)             |
| `installdisk.disks[0].partitions[0].mkfs_opts`   | str  | argument to the `opts` parameter of the [community.general.filesystem](https://docs.ansible.com/projects/ansible/latest/collections/community/general/filesystem_module.html)                 |
| `installdisk.disks[0].partitions[0].mountpoint`  | str  | argument to the `path` parameter of the [ansible.posix.mount](https://docs.ansible.com/projects/ansible/latest/collections/ansible/posix/mount_module.html) module                            |
| `installdisk.disks[0].partitions[0].mount_opts`  | str  | argument to the `opts` parameter of the [ansible.posix.mount](https://docs.ansible.com/projects/ansible/latest/collections/ansible/posix/mount_module.html) module                            |
| `installdisk.disks[0].partitions[0].mount_order` | int  | mount order. Mount order, filesystems are mounted from lowest to highest.                                                                                                                     |
| `installdisk.lvm_layout`                         | list | list of dicts describing the lvm layout of the disks                                                                                                                                          |
| `installdisk.lvm_layout[0].vg`                   | str  | argument to the same named parameter of the [community.general.lvg](https://docs.ansible.com/projects/ansible/latest/collections/community/general/lvg_module.html) module                    |
| `installdisk.lvm_layout[0].pvs`                  | list | argument to the same named parameter of the [community.general.lvg](https://docs.ansible.com/projects/ansible/latest/collections/community/general/lvg_module.html) module                    |
| `installdisk.lvm_layout[0].lvs`                  | list | list of dicts describing the logical volumes for this volume group                                                                                                                            |
| `installdisk.lvm_layout[0].lvs[0].lv`            | str  | argument to the same named parameter of the [community.general.lvol](https://docs.ansible.com/projects/ansible/latest/collections/community/general/lvol_module.html) module                  |
| `installdisk.lvm_layout[0].lvs[0].size`          | str  | argument to the same named parameter of the [community.general.lvol](https://docs.ansible.com/projects/ansible/latest/collections/community/general/lvol_module.html) module                  |
| `installdisk.lvm_layout[0].lvs[0].fstype`        | str  | argument to the same named parameter of the [community.general.filesystem](https://docs.ansible.com/projects/ansible/latest/collections/community/general/filesystem_module.html)             |
| `installdisk.lvm_layout[0].lvs[0].mkfs_opts`     | str  | argument to the `opts` parameter of the [community.general.filesystem](https://docs.ansible.com/projects/ansible/latest/collections/community/general/filesystem_module.html)                 |
| `installdisk.lvm_layout[0].lvs[0].mount_opts`    | str  | argument to the `opts` parameter of the [ansible.posix.mount](https://docs.ansible.com/projects/ansible/latest/collections/ansible/posix/mount_module.html) module                            |
| `installdisk.lvm_layout[0].lvs[0].mount_order`   | int  | order indication. mount order goes from low to high                                                                                                                                           |
| `installdistribution`                            | dict | Dict describing the distribution to be installed.                                                                                                                                             |
| `installdistribution.name`                       | str  | The name of the distribution. The combination `name` and `version` corresponds to the distribution file in `vars/`                                                                            |
| `installdistribution.version`                    | str  | The version of the distribution. The combination `name` and `version` corresponds to the distribution file in `vars/`                                                                         |
| `installdistribution.repo`                       | dict | Optional dict describing an override for the `repo` described in the `vars/` for the combination of `name` and `version` of this `installdistribution`                                        |
| `installdistribution.repo.type`                  | str  | Type of the repository URL. Either `metalink`, `mirrorlist` or `baseurl`                                                                                                                      |
| `installdistribution.repo.url`                   | str  | URL for the repository. This should be a BaseOS repository.                                                                                                                                   |
| `rootpw`                                         | str  | The root password for the installed OS. Should be set in a vault...                                                                                                                           |
> :warning:
By using this role, the disks specified by `installdisk` will be destroyed without asking for confirmation!!!

#### Example installdisk:
```
installdisk:
  disks:
    - device: /dev/vda
      label: gpt
      partitions:
        - id: boot
          number: 1
          part_start: 1MiB
          part_end: 1024MiB
          fstype: ext4
          mkfs_opts: "-L boot -O ^orphan_file"
          mountpoint: /boot
          mount_opts: defaults
          mount_order: 20

        - id: efi
          number: 2
          part_start: 1024MiB
          part_end: 2GiB
          fstype: fat32
          mkfs_opts: "-n EFI"
          mountpoint: /boot/efi
          mount_opts: "umask=0077,shortname=winnt"
          mount_order: 30

        - id: pv.01
          number: 3
          part_start: 2GiB
          part_end: 100%
          flags:
            - lvm

  lvm_layout:
    - vg: vg.rh
      pvs:
        - pv.01
      lvs:
        - lv: swap
          size: 512M
          fstype: swap
          mkfs_opts: "-L swap"

        - lv: root
          size: 100%FREE
          fstype: ext4
          mkfs_opts: "-L root -O ^orphan_file"
          mountpoint: /
          mount_opts: defaults
          mount_order: 10
```

#### example installdistribution
```
installdistribution:
  name: rocky
  version: "9"
  repo:
    type: mirrorlist
    url: https://mirrors.rockylinux.org/mirrorlist?arch=x86_64&repo=BaseOS-9&country=ch
```
_`repo` is optional but defaults to the general mirrorlist of the distribution. An added `country=` can improve download speed and reliability._

## Optional variables

Below the list of Optional `host_vars`, followed by more extensive explanation and an example for each.

| Variable               | Type |                                                                         Description                                                                                                     |
|------------------------|------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `root_authorized_keys` | list | A list of ssh pub keys to be added to the `authorized_keys` file of the root user. This list is added to the list off ssh keys of [dracut-sshd](https://github.com/gsauthof/dracut-sshd)|
| `strict_selinux`       | bool | To indicate if the installed system should have SELinux enabled.                                                                                                                        |
| `continue_install`     | bool | To indicate what the initramfs is supposed to do after install is finished.                                                                                                             |

### root_authorized_keys
The `root_authorized_keys` variable is a list of public ssh keys that are added for the root user of the installed system. This list is added to the authorized_keys that are installed in the initramfs by `dracut-sshd`.

#### Example:

```
root_authorized_keys:
- 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILsoXSAw7Gfqfk9tMQiAmSLRMXI1jZ/tpOjQ6OMRzd5J rocky@localhost.localdomain'
```

### strict_selinux & continue_install
`strict_selinux: true` : When `strict_selinux` has been chosen, then for the first boot of the system, independently of our choice for `continue_install`, we have to bear in mind the `strict_selinux` setting we have choosen.
Depending on the distribution, it might be required to have the first boot in a `selinux` `permissive` mode. To realize this we can add `enforcing=0` to the kernel arguments of grub.

With the `continue_install` host_var we can control what should happen after the minimal install is finished.<br>
Either:
* power-off the machine and wait for the admin to detach the initramfs to boot the freshly installed system.
* tell dracut to continue its normal flow of operation and finish the boot of the freshly installed system. After the boot is finished, we can continue our setup using Ansible.

`continue_install: true` : When we choose to let dracut continue its normal flow of  operation after the minimal install is finished, first of all we need the same kernel version available in the freshly installed system.
For this, the currently active kernel version, the one used to boot the initramfs, is added to the kernel package in the `minimalpackages` list of the `distribution` var.
This can cause the `geertsky.tuxifier.generate_minimal_install_urls_info` module to fail in resolving the URLs to the `minimalpackages` when the major version of the distribution used to generate the initramfs is not the same as the major version of the distribution that is being installed.
Additionally, it can be that the kernel version used to generate the initramfs is not the latest available for this distribution. When that happens it means that the installation performed is not the latest available.

## role vars
In the role a number of variables are defined in different var files.
### main.yml

| Variable                                       | Type | Description                                                                                                                                                                      |
|------------------------------------------------|------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| ansible_interpreter_python_fallback | list | The `ansible_interpreter_python_fallback` var is extended with the python interpreter of the tuxifier-python environment available in the initramfs                                         |
| rpm_argv | list | The arguments list to the rpm commands executed by `tuxifier`                                                                                                                                                          |
| virtual_filesystems | list | The list of virtual filesystems mounted in the `/tuxifier-sysroot` for the installation.                                                                                                                    |

### {{ distribution.name + distribution.version }}.yml Distribution vars

The distribution variable are set in a file named `{{distribution.name + distribution.version }}.yml` so for rocky 9 it would be `rocky9.yml`.
In such a distribution file the following variable are set:
| Var                          | Type | Value                                                                                          |
|------------------------------|------|------------------------------------------------------------------------------------------------|
| rpmdb_reimport               | bool | `rpmdb_reimport` controls if the rpmdb is reimported after installation.                       |
| distribution                 | dict | The distribution dict describes the distribution to install.                                   |
| distribution.name            | str  | The `name` of the distribution.                                                                |
| distribution.version         | str  | The `version` of the distribution.                                                             |
| distribution.arch            | str  | The `architecture` to install.                                                                 |
| distribution.repo            | dict | The `repo` dictionary is describes the repository where the packages can be retrieved.         |
| distribution.repo.type       | str  | The `type` of URL used for this repository.                                                    |
| distribution.repo.url        | str  | The `url` to the repository.                                                                   |
| distribution.minimalpackages | list | The `minimalpackages` list of packages to install for a minimal install.                       |
| gpg_key                      | str  | The path to the GPG key relative to the `files/` directory to verify the validity of the rpms. |


### Example host_vars

```
installdistribution:
  name: rocky
  version: "9"

root_authorized_keys:
  - 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOm4c78woS/1JU/A+jeAuKjuThZSH7qUbzuS+ldogq2v geert@clt-mgt05'

strict_selinux: true # Touches /.autorelabel

continue_install: false # When true, then it needs kernel version == installed kernel version. This is forced by tuxifier.

rootpw: rootpw
installdisk:
  disks:
    - device: /dev/vda
      label: gpt
      partitions:
        - id: bios_grub
          number: 1
          part_start: 1MiB
          part_end: 2MiB
          flags:
            - bios_grub
        - id: boot
          number: 2
          part_start: 2MiB
          part_end: 1024MiB
          fstype: ext3
          mkfs_opts: "-L boot -O ^orphan_file"
          mountpoint: /boot
          mount_opts: defaults
          mount_order: 20

        - id: pv.01
          number: 3
          part_start: 2GiB
          part_end: 100%
          flags:
            - lvm

  lvm_layout:
    - vg: vg.rh
      pvs:
        - pv.01
      lvs:
        - lv: swap
          size: 512M
          fstype: swap
          mkfs_opts: "-L swap"

        - lv: root
          size: 100%FREE
          fstype: ext4
          mkfs_opts: "-L root -O ^orphan_file"
          mountpoint: /
          mount_opts: defaults
          mount_order: 10
```

## License

EUPL 1.2

## Author Information

Geert Geurts `<geert@verweggistan.eu>`
