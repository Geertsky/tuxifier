ansible-install_initramfs
=========================
This role makes it possible to fulfill a minimal install of a distribution using Ansible from within the initramfs. A customized initramfs image needs to be generated as described in the Requirements section below. This initramfs image in combination with its kernel need to be fed to the server by any way possible. For instance: PXE, qemu/kvm Direct kernel boot.


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

The generation of the custom initramfs consists of two parts.<br> 
- First we'll create an installation of some tools we need in the initramfs to a temporary directory. 
- Then we build an initramfs in which we include all the files from this temporary directory.

### Installation of tools to a temporary directory

To install all the necessary tools to a temporary directory we can issue the following command:

```
mkdir -p /tmp/initrd/etc/dnf/
cp /etc/yum.repos.d/fedora.repo /tmp/initrd/etc/dnf/dnf.conf 
cat /etc/dnf/dnf.conf >> /tmp/initrd/etc/dnf/dnf.conf 
dnf --assumeyes --config /tmp/initrd/etc/dnf/dnf.conf --setopt=reposdir=/tmp/initrd/etc/yum.repos.d/ --releasever 38 install --installroot /tmp/initrd dnf python3 python3-dnf python3-libselinux parted dosfstools e2fsprogs util-linux xfsprogs lvm2
rm -Rf /tmp/initrd/etc/!("pki"|"dnf")
mkdir -p /tmp/initrd/etc/ssh
sed 's/Subsystem.*sftp.*/Subsystem       sftp    internal-sftp/' /etc/ssh/sshd_config> /tmp/initrd/etc/ssh/sshd_config
cd /tmp/initrd/usr/sbin
for F in $(ls -l /usr/sbin/|grep '\-> lvm'|awk '{print $(NF-2)}'); do ln -s lvm $F; done
```

The above scriptlet does the following:
-  Generate a `dnf.conf` in which the repositories from a default `fedora.repo` are defined.
- Install `dnf`, `python3`, `python3-dnf`, `parted` `lvm2` and some programs to create file systems (`mkfs.*`).
- Remove all the files in `/etc` except for the `pki` and `dnf` sub-directories. The `pki` directory is needed because of the rpm GPG-keys it contains. The `dnf` directory is needed because we need a repository for our installation.
- Install a modified `/etc/ssh/sshd_config` so it uses the in-process SFTP server.
- The for loop is used to manually create the links for all `lvm` commands that are linked to `lvm`. Somehow the `dracut` `lvm` module didn't do this.

Now our temporary installation directory is finished, and we can continue with generating the initramfs image.

### Building the initramfs image

We can generate the initramfs image using the following command:

```
dracut -NM -a "sshd network lvm systemd-resolved" -i /tmp/initrd / /home/geert/work/ansible-initrd/initramfs-$(uname -r).img $(uname -r) --force
```
*The above command writes the initramfs image to `/home/geert/work/ansible-initrd/` directory. You can change this as you see fit.*

The following dracut modules are added:
|dracut module     |explanation                                                           |
|------------------|----------------------------------------------------------------------|
|`sshd`            | For ssh access to the initramfs we use the [dracut-sshd](https://github.com/gsauthof/dracut-sshd) module from **gsauthof**|
|`network`         | We need the network to be active inside the initramfs.                |
|`lvm`             | We want `lvm` support. (The linking of the commands was done manually)|
|`systemd-resolved`|We want to be able to resolve names inside the initramfs.              |


Role Variables
--------------

For the installation of the OS a number of packages are required. In the `vars/` directory these are defined in `<distribution><distribution version>.yml`.

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
The var `installdistribution` is a dictionary with two items:
* `name` The name of the distribution
* `version` The version of the distribution

Example:

```
installdistribution:
  name: rocky
  version: 8
```

Root_authorized_keys
--------------------
The `root_authorized_keys` var is a list of ssh pub-keys to be added to the `authorized_keys` file for the root user.

Example:
--------

```
root_authorized_keys:
  - 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDlUb4UApMweLjlbmAadiwjPNwAiZ0i/ucxN9sk50kur geert@verweggistan.eu'
```

Dependencies
------------

A list of other roles hosted on Galaxy should go here, plus any details in regards to parameters that may need to be set for other roles, or variables that are used from other roles.

Example Playbook
----------------

Including an example of how to use your role (for instance, with variables passed in as parameters) is always nice for users too:

    - hosts: servers
      roles:
         - { role: username.rolename, x: 42 }

License
-------

BSD

Author Information
------------------

An optional section for the role authors to include contact information, or a website (HTML is not allowed).
