ansible-bambini
=========================
The `ansible-bambini` role makes a Bare Metal minimal Install of a distribution using Ansible using a initial ramdisk created using dracut and the [dracut-bambini](https://github.com/Geertsky/dracut-bambini) module. This initramfs image in combination with its kernel need to be fed to the server by any way possible. For instance: PXE, qemu/kvm Direct kernel boot, customized grub.

whetting your appetite
----------------------
[youtube demonstration of an ansible minimal Bare Metal Install using bambini](https://youtu.be/7qW9YJ4XMa4)

Requirements
------------

Collection requirements
-----------------------
There are two collections that need to be installed:
* community.general
* ansible.posix

They can be installed with the following two commands:

```
ansible-galaxy collection install community.general
ansible-galaxy collection install ansible.posix
```

Initramfs image generation
--------------------------

See: the [dracut-bambini](https://github.com/Geertsky/dracut-bambini) git repository for the steps to create the initramfs

Role Variables
--------------

Mandatory variables
-------------------

Below the list of Mandatory role variables, followed by more extensive explanation and an example for each.

|Variable|Description|
|---------------------|-----------------------------------------------------------------------------------|
|`installdisk`        |points to the blockdevice to be partitioned and used for the installation of the OS|
|`installdistribution`|A two items dictionary with the distribution `name` and `version` to be installed. |
|`rootpw`             |The root password for the installed OS. Should be set in a vault...                |

Installdisk
-----------
For partitioning and installation of the OS the `installdisk` var needs to be set to the blockdevice used for installation.

> :warning:
By using this role, the disk specified by `installdisk` will be destroyed without asking for confirmation!!!

Example:
--------

```
installdisk: /dev/vda
```

Installdistribution
-------------------
The `installdistribution` var is a dictionary with two items:
* `name` The name of the distribution
* `version` The version of the distribution

Example:

```
installdistribution:
  name: rocky
  version: 8
```

Optional variables
------------------

Below the list of Optional role variables, followed by more extensive explanation and an example for each.

|Variable|Description|
|--------|-----------|
|root_authorized_keys|A list of ssh pub keys to be added to the `authorized_keys` file of the root user|

Root_authorized_keys
--------------------
The `root_authorized_keys` var is a list of ssh pub-keys to be added to the `authorized_keys` file for the root user.

Example:
--------

```
root_authorized_keys:
  - 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDlUb4UApMweLjlbmAadiwjPNwAiZ0i/ucxN9sk50kur geert'
```

For the installation of the OS a number of packages are required. In the `vars/` directory these are defined in `<distribution><distribution version>.yml`.

Dependencies
------------

A list of other roles hosted on Galaxy should go here, plus any details in regards to parameters that may need to be set for other roles, or variables that are used from other roles.

Example Playbook
----------------
```
---
- hosts: installer
  vars_files:
    - vault.yml
  roles:
    - role: "/home/geert/git/geertsky/ansible-bambini/"
```
Example host_vars
-----------------

```
installdisk: /dev/vda

installdistribution:
  name: rocky
  version: 8

root_authorized_keys:
  - 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDlUb4UApMweLjlbmAadiwjPNwAiZ0i/ucxN9sk50kur geert
```

License
-------

BSD

Author Information
------------------

Geert Geurts `<geert AT verweggistan.eu>`
