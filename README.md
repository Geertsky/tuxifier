# ansible-install_initramfs

A typical workflow for an ansible installation of a machine is as follows:

- Perform a minimal install of a machine using for instance a kickstart file.
- Boot the freshly installed machine.
- Modify the installation using ansible.

When we boot however a customized initial ramdisk image, we can perform the partitioning step, the mininimal install step and the modify install steps all from the same playbook. This makes the need for different minimal install concepts obsolete. This for instance makes my [Generic kickstart file](https://github.com/Geertsky/kickstart) obsolete... Furthermore it makes the installation of machines completely controlled by ansible. Additionally, it is faster and less error prone.

Below the steps to create this modified initramfs + a playbook with a proof-of-concept. This proof-of-concept could be extended with an additional part which makes use of the `community.general.chroot` connection plugin to implement the "Modify the installation using ansible" step.

This proof-of-concept is done with `fedora 38` for an installation of `fedora 38`. It should be similar for different operating systems, and they could possibly be mixed as well.

## Requirements

For this proof-of-concept we need two ansible galaxy collections. They can be install with the following commands:

```
ansible-galaxy collection install community.general
ansible-galaxy collection install ansible.posix
```

## Generation of the initramfs

The generation of the custom initramfs consists of two parts.<br> 
- First we'll create an installation of some tools we need in the initramfs to a temporary directory. 
- Then we build an initramfs in which we include all the files from this temporary directory.

### Installation of tools to a temporary directory

To install all the necessary tools to a temporary directory we can issue the following command:

```
mkdir -p /tmp/initrd/etc/dnf/
cp /etc/yum.repos.d/fedora.repo /tmp/initrd/etc/dnf/dnf.conf 
cat /etc/dnf/dnf.conf >> /tmp/initrd/etc/dnf/dnf.conf 
dnf --assumeyes --config /tmp/initrd/etc/dnf/dnf.conf --setopt=reposdir=/tmp/initrd2/etc/yum.repos.d/ --releasever 38 install --installroot /tmp/initrd python3 python3-dnf python3-libselinux parted btrfs-progs dosfstools e2fsprogs exfatprogs hfsplus-tools ntfsprogs util-linux xfsprogs
rm -Rf /tmp/initrd/etc/!("pki"|"dnf")
mkdir -p /tmp/initrd/etc/ssh
sed 's/Subsystem.*sftp.*/Subsystem       sftp    internal-sftp/' /etc/ssh/sshd_config> /tmp/initrd/etc/ssh/sshd_config
cd /tmp/initrd/usr/sbin
for F in $(ls -l /usr/sbin/|grep '\-> lvm'|awk '{print $(NF-2)}'); do ln -s lvm $F; done
```

The above scriptlet does the following:
-  Generate a `dnf.conf` in which the repositories from a default `fedora.repo` are defined.
- Install `python3`, `python3-dnf`, `parted` and some programs to create file systems (`mkfs.*`).
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

## proof-of-concept

I've developed this installation method using the "Direct kernel boot" feature of `libvirt` (*Virtual Machine Manager->double-click VM->Show virtual hardware details->Boot Options->Direct kernel boot*), but you can as well use different methods like a setup of a PXE server that servers this initramfs together with a kernel.

### kernel cmdline options

There are three additional kernel commandline options required for using this initramfs:

|kernel option       | description                                                                           |
|--------------------|---------------------------------------------------------------------------------------|
|`rd.break=pre-pivot`|Causes dracut to stop execution just before it is about to chroot to the actual rootfs.|
|`rd.neednet=1`      |We need network access to the initramfs                                                |
|`ip=dhcp`           |We want to receive an ip over `dhcp`                                                   |

*The ip can be set statically, as well as other dracut options. See: [dracut.cmdline](https://man7.org/linux/man-pages/man7/dracut.cmdline.7.html)(7)*

### booting the initramfs

When we boot the machine to be installed with this initramfs, we are quite quickly informed the boot process was halted because the `rd.break=pre-pivot` kernel cmdline option. That means the `sshd` is up and running and we can access the initramfs. And thus continue with `ansible` from here on!

### Ansible inventory

The initramfs advertises the hostname `installer` thus our inventory file can look as follows:

`inventory/hosts.yml`
```
proof_of_concept:
  hosts:
    installer
```

`files`
For the `proof-of-concept.yml` playbook a number of files are added:
|File                                            |Description                                                                     |
|------------------------------------------------|--------------------------------------------------------------------------------|
|`files/dnf.conf`                                |A configuration file for dnf containing the repositories from `fedora.repo`     |
|`files/etc/systemd/system/reset-selinux.service`|A service file to trigger the `reset-selinux.sh` script                         |
|`files/usr/local/sbin/reset-selinux.sh`         |A script that reset selinux to `enforcing` and deletes itself and the service file|

### The `proof-of-concept.yml` playbook

The `proof-of-concept.yml` playbook contains the following tasks:

|Task                                                        |Description                                                         |
|------------------------------------------------------------|--------------------------------------------------------------------|
|`"Read vda device information (always use unit when probing)"`|Gather info from `/dev/vda`                                       |
|`"Remove a volume group with name vg.rh"`                     |Remove all lvm volumes                                            |
|`"Remove all partitions from disk"`                           |Remove all partitions                                             |
|`"Create a new primary partition with a size of 600MiB"`      |Create a primary partition                                        |
|`"Create a new primary partition with a size of 1GiB"`        |Create a primary partition                                        |
|`"Create a new primary LVM partition with a size rest"`       |Create a primary partition                                        |
|`"Create or resize a volume group on top of /dev/vda3"`       |Create a volume group                                             |
|`"Create a logical volume root"`                              |Create a logical volume "root"                                    |
|`"Create a logical volume swap"`                              |Create a logical volume "swap"                                    |
|`"Create a xfs file system on /dev/vda1"`                      |Create a `xfs` file system on `/boot`                             |
|`"Create a vfat file system on /dev/vda2"`                     |Create a `vfat` file system on `/boot/efi`                           |
|`"Create a swap file system on /dev/vg.rh/swap"`               |Create a swap file system                                          |
|`"Create a xfs file system on /dev/vg.rh/root"`                |Create a `xfs` file system on `/`                                 |
|`"Mount up device /mnt"`                                      |Mount `/mnt`                                                      |
|`"Mount up device /mnt/boot"`                                 |Mount `/mnt/boot`                                                 |
|`"Mount up device /mnt/boot/efi"`                             |Mount `/mnt/boot/efi`                                             |
|`"Install dnf config"`                                        |Install `/mnt/etc/dnf/dnf.conf`                                   |
|`"Install genfstab"`                                          |Download [genfstab](https://github.com/glacion/genfstab/tree/master) from **glacion**|
|`"Install minimal, kernel and grub"`                          |Install a `minimal OS` + `kernel` + `grub`                        |
|`"Bind mount /dev /sys and /proc"`                            |Bind mount `/dev`, `/sys` and `/proc`                             |
|`"Touch .autorelabel"`                                        |Trigger a `selinux` relabel on reboot                             |
|`"Genarate /etc/fstab"`                                      |Generate fstab using [genfstab](https://github.com/glacion/genfstab/tree/master) from **glacion**|
|`"Install grub2 /boot/grub2/grub.cfg"`                      |Install `/boot/grub2/grub.cfg`                                      |
|`"Install grub2 /boot/efi/EFI/fedora/grub.cfg"`             |Install `/boot/efi/EFI/fedora/grub.cfg`                             |
|`"Install grub2 /etc/grub2-efi.cfg"`                        |Install `/etc/grub2-efi.cfg`                                        |
|`"Set root password"`                                       |Set the root password to `password` (could be done fancier with a vault)|
|`"Finalize the installation"`                               |Power down the machine                                              |

## selinux

Because selinux is not yet active at initramfs runtime, all file systems need to be relabeled. This is done by touching `/.autorelabel` in the task `"Touch .autorelabel"`. This causes a relabel at first boot, followed by a reboot.

## Quick start

* Create an initramfs as described in [Generation of the initramfs](#generation-of-the-initramfs)
* Boot a machine with the generated initramfs and kernel cmdline options: `rd.break=pre-pivot ip=dhcp rd.neednet=1` (*Virtual Machine Manager->double-click the VM->Show virtual hardware details->Boot Options->Direct kernel boot->Enable direct kernel boot, Kernel path, initrd path, Kernel args*)
* Clone this repository: `git clone git@github.com:Geertsky/ansible-install_initramfs.git; cd ansible-install_initramfs`
* Run ansible: `ansible-playbook -i inventory/hosts.yml proof-of-concept.yml`
* When the machine is finished installing it powers off. Remove the option to boot the custom initramfs and kernel (*Virtual Machine Manager->double-click VM->Show virtual hardware details->Uncheck "Enable direct kernel boot"*) and boot the machine.
* After the relabeling the machine reboots once to complete the installation.
