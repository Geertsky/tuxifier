# ansible-bambini

`ansible-bambini` makes the bare metal installation of machines completely controlled by ansible. Additionally, it is faster and less error prone.

A typical workflow for a bare metal installation of a machine is as follows:

- Perform a minimal install of a machine using for instance a kickstart file.
- Boot the freshly installed machine.
- Modify the installation using ansible.

That is two out of three, ok quite minor, but still manual tasks to perform.
With the [dracut-bambini](https://github.com/Geertsky/dracut-bambini) dracut module, we can hold the boot execution just before the root filesystem gets mounted so we can use ansible to partition the disk and install a minimal OS.
The `ansible-bambini` role is designed to do exactly that. It partitions a disk, installs a minimal OS, and waits for the boot process to finish.

## whetting your appetite
[youtube demonstration](https://youtu.be/7qW9YJ4XMa4) of an ansible bare metal install using bambini

## Dependencies

## Collection dependencies

## Initramfs image generation

See: the [dracut-bambini](https://github.com/Geertsky/dracut-bambini) git repository for the steps to create the initramfs

## Role Variables

## Mandatory variables

Below the list of Mandatory role variables, followed by more extensive explanation and an example for each.

|Variable|Description|
|---------------------|-----------------------------------------------------------------------------------|
|`installdisk`        |points to the blockdevice to be partitioned and used for the installation of the OS|
|`installdistribution`|A two items dictionary with the distribution `name` and `version` to be installed. |
|`rootpw`             |The root password for the installed OS. Should be set in a vault...                |

### Installdisk
For partitioning and installation of the OS the `installdisk` var needs to be set to the blockdevice used for installation.

> :warning:
By using this role, the disk specified by `installdisk` will be destroyed without asking for confirmation!!!

#### Example:
```
installdisk: /dev/vda
```

### Installdistribution
The `installdistribution` var is a dictionary with two items:
* `name` The name of the distribution
* `version` The version of the distribution

#### Example:

```
installdistribution:
  name: rocky
  version: 8
```

## Optional variables

Below the list of Optional role variables, followed by more extensive explanation and an example for each.

|Variable|Description|
|--------|-----------|
|root_authorized_keys|A list of ssh pub keys to be added to the `authorized_keys` file of the root user|

### Root_authorized_keys
The `root_authorized_keys` var is a list of ssh pub-keys to be added to the `authorized_keys` file for the root user.

#### Example:

```
root_authorized_keys:
  - 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDlUb4UApMweLjlbmAadiwjPNwAiZ0i/ucxN9sk50kur geert'
```

For the installation of the OS a number of packages are required. In the `vars/` directory these are defined in `<distribution><distribution version>.yml`.

### Example Playbook
```
---
- hosts: installer
  vars_files:
    - vault.yml
  roles:
    - role: "/home/geert/git/geertsky/ansible-bambini/"
```
### Example host_vars

```
installdisk: /dev/vda

installdistribution:
  name: rocky
  version: 8

root_authorized_keys:
  - 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDlUb4UApMweLjlbmAadiwjPNwAiZ0i/ucxN9sk50kur geert
```

## License

BSD

## Author Information

Geert Geurts `<geert AT verweggistan.eu>`
