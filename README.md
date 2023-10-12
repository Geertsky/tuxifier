# ansible-install_initramfs

A typical workflow for an ansible installation of a machine is as follows:

- Perform a minimal install of a machine using for instance a kickstart file.
- Boot the freshly installed machine.
- Modify the installation using ansible.

When we boot a customized initial ramdisk image, we can perform the partitioning the mininimal install and the modify install steps all from the same playbook. This makes my [Generic kickstart file](https://github.com/Geertsky/kickstart) obsolete.

Below the steps to create this modified initramfs plus a playbook with a proof-of-concept. This proof-of-concept could be extended with an additional part which makes use of the `community.general.chroot` connection plugin to finalize the last of the three steps mentioned above.

This proof-of-concept is done with fedora 38 for an installation of fedora 38. It should be similar for different operating systems, and they could possibly be mixed as well.

## Generation of the initramfs

The generation of the custom initramfs consists of two parts. First we'll create a installation of some tools we need in the initramfs to a temporary directory. Then we build an initramfs in which we include all the files from this temporary directory.

### Installation of tools to a temporary directory

To install all the necesary tools to a temporary directory we can issue the following command:

```
mkdir -p /tmp/initrd/etc/dnf/
cp /etc/yum.repos.d/fedora.repo /tmp/initrd/etc/dnf/dnf.conf 
cat /etc/dnf/dnf.conf >> /tmp/initrd/etc/dnf/dnf.conf 
dnf -c /tmp/initrd/etc/dnf/dnf.conf --releasever 38 install --installroot /tmp/initrd python3 python3-dnf python3-libselinux parted btrfs-progs dosfstools e2fsprogs exfatprogs hfsplus-tools ntfsprogs util-linux xfsprogs
rm -Rf /tmp/initrd/etc/!("pki"|"dnf")
mkdir -p /tmp/initrd/etc/ssh
sed 's/Subsystem.*sftp.*/Subsystem       sftp    internal-sftp/' /etc/ssh/sshd_config> /tmp/initrd/etc/ssh/sshd_config
cd /tmp/initrd/usr/sbin
for F in $(ls -l /usr/sbin/|grep '\-> lvm'|awk '{print $(NF-2)}'); do ln -s lvm $F; done
```

This generates a `dnf.conf` in which the repositories from `fedora.repo` are defined.
It then installs `python3`, `python3-dnf`, `python3-libselinux`, `parted` and some programs to create filesystems.
All the files in `/etc` are removed except for the `pki` and `dnf` sub-directories. The `pki` directory is needed because of the rpm GPG-keys it contains.
The `/etc/ssh/sshd_config` is modified so it uses the in-process SFTP server.
Then finaly the for loop is used to manually create the links for all `lvm` commands that are linked to `lvm`. Somehow the `dracut` `lvm` module didn't do this.

Now our temporary installation directory is finished, and we can continue with generating the initramfs image.

### Generating the initramfs image

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

I've developed this installation method using the "Direct kernel boot" feature of `libvirt`, but you can as well use different methods like a setup of a PXE server that servers this initramfs together with a kernel.

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
|`"Create a xfs filesystem on /dev/vda1"`                      |Create an `xfs` filesystem on `/boot`                             |
|`"Create a vfat filesystem on /dev/vda2"`                     |Create a vfat filesystem on `/boot/efi`                           |
|`"Create a swap filesystem on /dev/vg.rh/swap"`               |Create a swap filesystem                                          |
|`"Create a xfs filesystem on /dev/vg.rh/root"`                |Create an `xfs` filesystem on `/`                                 |
|`"Mount up device /mnt"`                                      |Mount `/mnt`                                                      |
|`"Mount up device /mnt/boot"`                                 |Mount `/mnt/boot`                                                 |
|`"Mount up device /mnt/boot/efi"`                             |Mount `/mnt/boot/efi`                                             |
|`"Install dnf config"`                                        |Install `/mnt/etc/dnf/dnf.conf`                                   |
|`"Install genfstab"`                                          |Download [genfstab](https://github.com/glacion/genfstab/tree/master) from **glacion**|
|`"Install minimal, kernel and grub"`                          |Install a `minimal OS` + `kernel` + `grub`                        |
|`"Bind mount /dev /sys and /proc"`                            |Bind mount `/dev`, `/sys` and `/proc`                             |
|`"Set selinux permissive"`                                    |Set `selinux` to `permissive`                                     |
|`"Touch .autorelabel"`                                        |Trigger a `selinux` relabel on reboot                             |
|`"Genarate /etc/fstab"`                                      |Generate fstab using [genfstab](https://github.com/glacion/genfstab/tree/master) from **glacion**|
|`"Install reset-selinux.service"`                           |Install a service to reset `selinux` back to `enforcing`            |
|`"Install reset-selinux.sh"`                                |Install the script to reset `selinux` back to `enforcing`           |
|`"Enable reset-selinux.service"`                            |Enable the `reset-selinux` service                                  |
|`"Install grub2 /boot/grub2/grub.cfg"`                      |Install `/boot/grub2/grub.cfg`                                      |
|`"Install grub2 /boot/efi/EFI/fedora/grub.cfg"`             |Install `/boot/efi/EFI/fedora/grub.cfg`                             |
|`"Install grub2 /etc/grub2-efi.cfg"`                        |Install `/etc/grub2-efi.cfg`                                        |
|`"Set root password"`                                       |Set the root password to `password` (could be done fancier with a vault)|
|`"Finalize the installation"`                               |Power down the machine                                              |

## Quick start

* Create an initramfs as described in [Generating the initramfs image](#generating-the-initramfs-image)
* Boot a machine with the generated initramfs and kernel cmdline options: `rd.break=pre-pivot ip=dhcp rd.neednet=1`
* Clone this repository: `git clone git@github.com:Geertsky/ansible-install_initramfs.git; cd ansible-install_initramfs`
* Run ansible: `ansible-playbook -i inventory/hosts.yml proof-of-concept.yml`
* When the machine is finished installing it powers off. Remove the option to boot a cusom kernel initramfs and boot the machine.
* After the relabeling the machine reboots once to complete the installation.
