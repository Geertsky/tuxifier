#!/bin/bash
echo 'LABEL=root	/	xfs	defaults,x-systemd.device-timeout=0 0 0' >/mnt/etc/fstab
echo 'LABEL=boot	/boot	xfs	defaults	0 0'>>/mnt/etc/fstab
echo '/dev/vda2		/boot/efi	vfat	umask=0077,shortname=winnt 0 2' >>/mnt/etc/fstab
