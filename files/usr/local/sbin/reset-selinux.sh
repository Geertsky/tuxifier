#!/bin/bash
sed -i -e '/^SELINUX/s/permissive/enforcing/' /etc/selinux/config
systemctl disable reset-selinux.service
rm -f /etc/systemd/system/reset-selinux.service
systemctl daemon-reload
rm -f "$0"
