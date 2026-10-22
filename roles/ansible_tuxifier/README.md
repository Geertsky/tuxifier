# ansible-tuxifier

```
Role belongs to geertsky/tuxifier
Namespace - geertsky
Collection - tuxifier
Version - 1.0.0
Repository - http://github.com/geertsky/tuxifier
```

Description: Partition and install a server from the initramfs built with dracut-incubator

## Dependencies

### Roles
The role [linux-system-roles.storage](https://github.com/linux-system-roles/storage) has to be installed as a role (not as the `fedora.linux_system_roles` collection),
for example with `ansible-galaxy role install linux-system-roles.storage` or from a git checkout in the `roles_path`. It is not a collection,
so it can not be listed in the `dependencies` of `galaxy.yml`.

### Initramfs image generation
For using `tuxifier`, the machine has to be booted using an initramfs image with the [dracut-incubator](https://github.com/geertsky/dracut-incubator) module included.
See: the [dracut-incubator](https://github.com/Geertsky/dracut-incubator) git repository for the steps to create the initramfs.

## Role Variables
### host_vars

| Variable                                         | Type | Description                                                                                                                                                                                   |
|--------------------------------------------------|------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `installdisk`                                    | list | The storage of the install target: a list of `storage_pools` exactly as accepted by the [linux-system-roles.storage](https://github.com/linux-system-roles/storage) role (`type: partition` or `lvm`). `mount_point`s are given as seen from the installed system (`/`, `/boot`, `/boot/efi`). |
| `installdisk_boot_disk`                          | str  | The disk to install the boot loader on. Optional. Defaults to the disk of the `partition` pool with the volume mounted at `/boot`, or else at `/boot/efi`.                                                                                         |
| `storage_disklabel_type`                         | str  | Variable of the storage role, e.g. `gpt`. Can be set in the host_vars as usual.                                                                                                              |
| `installdistribution`                            | dict | Dict describing the distribution to be installed.                                                                                                                                             |
| `installdistribution.name`                       | str  | The name of the distribution. The combination `name` and `version` corresponds to the distribution file in `vars/`                                                                            |
| `installdistribution.version`                    | str  | The version of the distribution. The combination `name` and `version` corresponds to the distribution file in `vars/`                                                                         |
| `installdistribution.repo`                       | dict | Optional dict describing an override for the `repo` described in the `vars/` for the combination of `name` and `version` of this `installdistribution`                                        |
| `installdistribution.repo.type`                  | str  | Type of the repository URL. Either `metalink`, `mirrorlist` or `baseurl`                                                                                                                      |
| `installdistribution.repo.url`                   | str  | URL for the repository. This should be a BaseOS repository.                                                                                                                                   |
| `rootpw`                                         | str  | The root password for the installed OS. Should be set in a vault...                                                                                                                           |
> :warning:
The storage is managed by the [linux-system-roles.storage](https://github.com/linux-system-roles/storage) role in
`storage_safe_mode: false`. Existing partitions, volume groups and filesystems on the disks specified by `installdisk` that
do not match the layout are removed without asking for confirmation, and `tuxifier_reinstall: true` wipes the disks first!!!

`installdisk` is passed as `storage_pools` to the storage role, so everything that role supports for partition and LVM pools
can be used. The storage role needs `python3-blivet` and its dependencies in the initramfs; its checks `blivet_available`,
`packages_installed` and `cryptsetup_services` are skipped (`storage_skip_checks`).

The storage role is called once, inside the private namespace of `/tuxifier-sysroot`, with the pools in the order listed. A pool
that uses a partition (`disks: [/dev/vda4]`) has to be listed after the `partition` pool that creates it. Existing volume groups
of `installdisk` are activated first, because the storage role does not activate them and would otherwise format the logical
volumes again on every run.

The storage role is given the pools without `mount_point`, so it only creates the block devices and neither mounts them nor
writes `/etc/fstab`. Tuxifier mounts the filesystems itself below `/tuxifier-sysroot`, sorted by mount point, so parents are
mounted before their children. The order of the pools and volumes does not matter for the mounts. These mounts are not written
to the `/etc/fstab` of the initramfs.

The `/etc/fstab` of the installed system, `/tuxifier-sysroot/etc/fstab`, gets an entry for every volume with a `mount_point`
and for every swap volume. The filesystems are identified as the storage role reports them, normally by `UUID=`.

For the boot loader of an EFI system the boot disk needs a `partition` pool with a volume with
`fs_type: efi`; its `name` is used as the partition number.

#### Example installdisk:
```
storage_disklabel_type: gpt
installdisk:
  - name: /dev/vda
    type: partition
    disks: [/dev/vda]
    volumes:
      - name: "1"
        size: 1MiB
        fs_type: biosboot

      - name: "2"
        size: 1GiB
        fs_type: ext4
        fs_label: boot
        fs_create_options: "-O ^orphan_file"
        mount_point: /boot
        mount_options: defaults

      - name: "3"
        size: 1GiB
        fs_type: efi
        fs_label: EFI
        mount_point: /boot/efi
        mount_options: "umask=0077,shortname=winnt"

      - name: "4"
        size: "0"     # the rest of the disk
        fs_type: lvmpv

  - name: vg.rh
    type: lvm
    disks: [/dev/vda4]
    volumes:
      - name: swap
        size: 512M
        fs_type: swap
        fs_label: swap

      - name: root
        size: 100%
        fs_type: ext4
        fs_label: root
        fs_create_options: "-O ^orphan_file"
        mount_point: /
        mount_options: defaults
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
| `tuxifier_reinstall`   | bool | Wipe the install disks before creating the storage layout. Default `false`.                                                                                                             |

### tuxifier_reinstall

When `true` (default `false`) the signatures of all disks in `installdisk` (the disks of the `partition` pools and the whole disks used by other pools) are wiped before the storage is created.
Without it the layout is only made to match, so re-running the role changes nothing. Meant to be passed on the command line:

```
ansible-playbook -e tuxifier_reinstall=true ...
```

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
This can cause the `geertsky.tuxifier.generate_minimal_install_info` module to fail in resolving the URLs to the `minimalpackages` when the major version of the distribution used to generate the initramfs is not the same as the major version of the distribution that is being installed.
Additionally, it can be that the kernel version used to generate the initramfs is not the latest available for this distribution. When that happens it means that the installation performed is not the latest available.

## role vars
In the role a number of variables are defined in different var files.
### main.yml

| Variable                                       | Type | Description                                                                                                                                                                      |
|------------------------------------------------|------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| ansible_interpreter_python_fallback | list | The `ansible_interpreter_python_fallback` var is extended with the python interpreter of the python-nest environment available in the initramfs                                         |
| rpm_macros | dict | The rpm macros defined for the rpm commands executed by `tuxifier`, as macro name and macro value, for example `_dbpath: /var/lib/rpm`. Macros named `_` followed by letters with an absolute path as value are created as directories in `/tuxifier-sysroot`                                                                                                                                                          |
| virtual_filesystems | list | The list of virtual filesystems mounted in the `/tuxifier-sysroot` for the installation.                                                                                                                    |

### {{ distribution.name + distribution.version }}.yml Distribution vars

The distribution variable are set in a file named `{{distribution.name + distribution.version }}.yml` so for rocky 9 it would be `rocky9.yml`.
In such a distribution file the following variable are set:
| Var                          | Type | Value                                                                                          |
|------------------------------|------|------------------------------------------------------------------------------------------------|
| rpmdb_reimport               | bool | `rpmdb_reimport` controls if the sqlite rpmdb, as written by the rpm of the initramfs, is exported and imported again with the rpm of the installed system. This gives distributions with another backend, such as bdb for version 8 of RHEL and its derivatives, an rpmdb in their own format.                       |
| distribution                 | dict | The distribution dict describes the distribution to install.                                   |
| distribution.name            | str  | The `name` of the distribution.                                                                |
| distribution.version         | str  | The `version` of the distribution.                                                             |
| distribution.arch            | str  | The `architecture` to install.                                                                 |
| distribution.efi_vendor_dir  | str  | The directory below `EFI/` on the ESP with the boot loader of the distribution (e.g. `redhat`, `rocky`, `opensuse`). |
| distribution.efi_loader      | str  | The file name of the shim EFI binary in `distribution.efi_vendor_dir` (e.g. `shimx64.efi`).     |
| distribution.grub_cfg        | str  | The path of the grub configuration read at boot, relative to the root of the installed system.  |
| distribution.grub_cfg_full_on_esp | bool | `true` when the grub.cfg on the ESP is the full configuration (RHEL 8 family); `false` when it is a stub referring to `distribution.grub_cfg`. |
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
storage_disklabel_type: gpt
installdisk:
  - name: /dev/vda
    type: partition
    disks: [/dev/vda]
    volumes:
      - name: "1"
        size: 1MiB
        fs_type: biosboot
      - name: "2"
        size: 1GiB
        fs_type: ext3
        fs_label: boot
        fs_create_options: "-O ^orphan_file"
        mount_point: /boot
      - name: "3"
        size: "0"
        fs_type: lvmpv

  - name: vg.rh
    type: lvm
    disks: [/dev/vda3]
    volumes:
      - name: swap
        size: 512M
        fs_type: swap
        fs_label: swap
      - name: root
        size: 100%
        fs_type: ext4
        fs_label: root
        fs_create_options: "-O ^orphan_file"
        mount_point: /
```

## License

EUPL 1.2

## Author Information

Geert Geurts `<geert@verweggistan.eu>`
