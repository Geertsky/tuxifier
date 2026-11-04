#!/usr/bin/env bash
# SPDX-License-Identifier: EUPL-1.2
# Start and stop the throwaway qemu VM of the tox envs "qemu-<distro>-...", booted from the incubator initramfs.
#
#   qemu-vm.sh start          boot the initramfs of QEMU_DISTRO on an empty install target (/dev/vda) and write
#                             $QEMU_WORKDIR/inventory.ini; ansible uses the python of python-nest
#   qemu-vm.sh restart        the same, on the install target the previous run left (the VM has powered off)
#   qemu-vm.sh wait-poweroff  wait until the VM has powered off (the initramfs does that after a finished install)
#   qemu-vm.sh permissive-first-boot  add enforcing=0 to the boot entries of the powered off install target (sudo)
#   qemu-vm.sh wait-installed  wait until the VM runs the installed system (continue_install=true: the initramfs boots on)
#   qemu-vm.sh poweroff-installed  power the running installed system off and wait for it
#   qemu-vm.sh boot-disk      boot the installed system from the install target; ansible uses the system python
#   qemu-vm.sh change-vars    print the extra vars of ansible-playbook for the distribution change test
#   qemu-vm.sh stop           power the VM off and remove its disk (QEMU_KEEP_DISK=1 keeps it)
#
# Environment:
#   QEMU_WORKDIR      directory for the disks, key, pid file and inventory (required)
#   QEMU_DISTRO       the distribution to install: rocky, rhel, almalinux or fedora with the major version, like rocky9
#                     or fedora44 (default: rocky9)
#   QEMU_INITRAMFS    the sysimage that the initramfs comes from, like rocky9 or rhel9 (default: the sysimage of
#                     QEMU_DISTRO if it exists, else the rocky one of the same major version, rocky10 for fedora)
#   QEMU_FIRMWARE     bios or uefi (default: bios)
#   QEMU_OVMF_CODE    OVMF firmware code for uefi (default: /usr/share/OVMF/OVMF_CODE.fd)
#   QEMU_OVMF_VARS    OVMF variables template for uefi (default: /usr/share/OVMF/OVMF_VARS.fd); every VM gets its own copy,
#                     that holds the boot entry the role makes with efibootmgr
#   QEMU_SCRATCH_SIZE size of the install target disk (default: 8G)
#   QEMU_LUKS_PASSPHRASE  the root is encrypted: boot-disk makes the serial console of the installed system the kernel
#                     console and types this passphrase when it is asked for
#   QEMU_EXTRA_KEY    boot-disk also writes inventory-extrakey.ini, that logs in with the second test key
#   QEMU_MIRROR       base url of the local mirror (see mirror-url.sh), for the repository of the distribution change test
#   QEMU_EXTRA_DISKS  number of extra disks /dev/vdb, /dev/vdc ... of QEMU_EXTRA_SIZE (default: 0, the raid layouts use 2)
#   QEMU_EXTRA_SIZE   size of an extra disk (default: 3G)
#   QEMU_MEMORY       memory in MiB (default: 2048)
# The initramfs images are built by initramfs.sh; see common.sh for the directories it uses.
set -euo pipefail
# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

: "${QEMU_WORKDIR:?QEMU_WORKDIR must be set}"
SCRATCH_SIZE="${QEMU_SCRATCH_SIZE:-8G}"
EXTRA_DISKS="${QEMU_EXTRA_DISKS:-0}"
EXTRA_SIZE="${QEMU_EXTRA_SIZE:-3G}"
MEMORY="${QEMU_MEMORY:-2048}"
DISTRO="${QEMU_DISTRO:-rocky9}"
if [[ -d "$SYSIMAGE_DIR/$DISTRO/lib/modules" ]]; then
    INITRAMFS_DISTRO="${QEMU_INITRAMFS:-$DISTRO}"
elif [[ "$DISTRO" == fedora* ]]; then
    INITRAMFS_DISTRO="${QEMU_INITRAMFS:-rocky10}"
else
    INITRAMFS_DISTRO="${QEMU_INITRAMFS:-rocky${DISTRO//[^0-9]/}}"
fi
FIRMWARE="${QEMU_FIRMWARE:-bios}"
OVMF_CODE="${QEMU_OVMF_CODE:-/usr/share/OVMF/OVMF_CODE.fd}"
OVMF_VARS="${QEMU_OVMF_VARS:-/usr/share/OVMF/OVMF_VARS.fd}"
case "$FIRMWARE" in
    bios) BOOT_PARTITION=2 ;; # biosboot, /boot
    uefi) BOOT_PARTITION=1 ;; # /boot, ESP
    *) echo "QEMU_FIRMWARE must be bios or uefi, not '$FIRMWARE'" >&2; exit 2 ;;
esac
PIDFILE="$QEMU_WORKDIR/qemu.pid"
# A unix socket path is limited to 107 bytes, the path of the work directory of a tox env is longer.
SERIAL_SOCK="/tmp/tuxifier-tests-$(printf %s "$QEMU_WORKDIR" | md5sum | cut -c1-12).serial"
MONITOR_SOCK="/tmp/tuxifier-tests-$(printf %s "$QEMU_WORKDIR" | md5sum | cut -c1-12).sock"

wait_for_ssh() {
    local key="$1" port="$2" tries="$3"
    echo "waiting for ssh on port $port"
    for _ in $(seq 1 "$tries"); do
        if ssh -i "$key" -p "$port" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
            -o BatchMode=yes -o ConnectTimeout=3 root@127.0.0.1 true 2> /dev/null; then
            echo "VM is up"
            return 0
        fi
        sleep 4
    done
    echo "VM did not come up in time, see $QEMU_WORKDIR/console.log" >&2
    if [[ -S "$MONITOR_SOCK" ]]; then
        echo "screendump $QEMU_WORKDIR/screen.ppm" | python3 -c '
import socket, sys
s = socket.socket(socket.AF_UNIX)
s.connect(sys.argv[1])
s.sendall(sys.stdin.read().encode() + b"\n")
' "$MONITOR_SOCK" || true
        sleep 1
        echo "screen of the VM: $QEMU_WORKDIR/screen.ppm" >&2
    fi
    return 1
}

# The extra disks are created by "start" and kept by "restart".
create_extra_disks() {
    local i
    for i in $(seq 1 "$EXTRA_DISKS"); do
        qemu-img create -q -f qcow2 "$QEMU_WORKDIR/extra$i.qcow2" "$EXTRA_SIZE"
    done
}

extra_disk_args() {
    local i
    for i in $(seq 1 "$EXTRA_DISKS"); do
        echo -drive "file=$QEMU_WORKDIR/extra$i.qcow2,if=virtio,format=qcow2"
    done
}

# Arguments of qemu for the firmware. The variables file is copied by "start" and kept by "restart", so the boot entry
# that the role makes survives the restarts.
firmware_args() {
    [[ "$FIRMWARE" == uefi ]] || return 0
    echo -drive "if=pflash,format=raw,unit=0,readonly=on,file=$OVMF_CODE" \
        -drive "if=pflash,format=raw,unit=1,file=$QEMU_WORKDIR/OVMF_VARS.fd"
}

# The port is free until another run takes it, so the choice and the start of qemu are done under a lock.
lock_ports() { exec 7> /tmp/tuxifier-tests-port.lock; flock 7; }
unlock_ports() { flock -u 7; }

# The serial console of the installed system is a socket when its root is encrypted: the passphrase is typed there.
serial_args() {
    if [[ -n "${QEMU_LUKS_PASSPHRASE:-}" ]]; then
        echo -chardev "socket,id=ser0,path=$SERIAL_SOCK,server=on,wait=off,logfile=$QEMU_WORKDIR/console.log" -serial chardev:ser0
    else
        echo -serial "file:$QEMU_WORKDIR/console.log"
    fi
}

# Types the passphrase at the serial console each time it is asked for (at most three times).
type_passphrase() {
    python3 - "$SERIAL_SOCK" "$QEMU_LUKS_PASSPHRASE" "${1:-600}" << 'PYEOF'
import re, socket, sys, time

path, passphrase, timeout = sys.argv[1], sys.argv[2].encode(), int(sys.argv[3])
deadline = time.time() + timeout
sock = socket.socket(socket.AF_UNIX)
while True:
    try:
        sock.connect(path)
        break
    except OSError:
        if time.time() > deadline:
            sys.exit("no serial console")
        time.sleep(0.5)
sock.settimeout(2)
seen = b""
sent = 0
while time.time() < deadline and sent < 3:
    try:
        data = sock.recv(4096)
    except socket.timeout:
        continue
    if not data:
        break
    seen += data
    if re.search(rb"enter passphrase", seen[-400:], re.I):
        time.sleep(0.5)
        sock.sendall(passphrase + b"\r")
        sent += 1
        print("typed the passphrase", sent)
        seen = b""
    elif b"login:" in seen:
        break
PYEOF
}

free_port() {
    python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])'
}

# The connection settings are group variables: the role adds a "<host>_chroot" host that only inherits the groups
# and ansible_host of the host, and has to reach the VM through the same forwarded port.
write_inventory() {
    local key="$1" port="$2" extra="${3:-}"
    cat > "$QEMU_WORKDIR/inventory.ini" <<EOF
[installer]
tuxifier-test ansible_host=127.0.0.1

[installer:vars]
ansible_port=$port
ansible_user=root
ansible_ssh_private_key_file=$key
ansible_ssh_common_args='-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'
$extra
EOF
}

start_initramfs() {
    local kernel initrd port
    eval "$("$TESTS_SCRIPTS_DIR/initramfs.sh" "$INITRAMFS_DISTRO" | grep -E '^(kernel|initrd)=')"
    kernel="$kernel"
    initrd="$initrd"
    [[ -n "${KEEP_DISK:-}" ]] || qemu-img create -q -f qcow2 "$QEMU_WORKDIR/target.qcow2" "$SCRATCH_SIZE"
    [[ -n "${KEEP_DISK:-}" ]] || create_extra_disks
    [[ -n "${KEEP_DISK:-}" || "$FIRMWARE" != uefi ]] || cp "$OVMF_VARS" "$QEMU_WORKDIR/OVMF_VARS.fd"
    lock_ports
    port="$(free_port)"
    # shellcheck disable=SC2046 # firmware_args prints separate words
    qemu-system-x86_64 -enable-kvm -cpu host -smp 2 -m "$MEMORY" -display none -daemonize $(firmware_args)  \
        -pidfile "$PIDFILE" -serial "file:$QEMU_WORKDIR/console.log" \
        -kernel "$kernel" -initrd "$initrd" \
        -append "rd.neednet=1 ip=dhcp root=LABEL=root enforcing=0 console=ttyS0" \
        -drive "file=$QEMU_WORKDIR/target.qcow2,if=virtio,format=qcow2" $(extra_disk_args) \
        -nic "user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:$port-:22"
    unlock_ports
    write_inventory "$TEST_KEY" "$port" "ansible_python_interpreter=/local/conda/envs/python-nest/bin/python3"
    wait_for_ssh "$TEST_KEY" "$port" 60
}

boot_disk() {
    local port http_port
    [[ -s "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2> /dev/null && { echo "VM still running" >&2; exit 1; }
    lock_ports
    port="$(free_port)"
    # the web server of the demo site is forwarded too; another port than the one of ssh
    http_port="$(free_port)"
    while [[ "$http_port" == "$port" ]]; do http_port="$(free_port)"; done
    # shellcheck disable=SC2046 # firmware_args and serial_args print separate words
    qemu-system-x86_64 -enable-kvm -cpu host -smp 2 -m "$MEMORY" -display none -daemonize $(firmware_args) $(serial_args) \
        -pidfile "$PIDFILE" \
        -monitor "unix:$MONITOR_SOCK,server,nowait" \
        -drive "file=$QEMU_WORKDIR/target.qcow2,if=virtio,format=qcow2" $(extra_disk_args) \
        -nic "user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:$port-:22,hostfwd=tcp:127.0.0.1:$http_port-:80"
    unlock_ports
    write_inventory "$TEST_KEY" "$port" "demo_http_port=$http_port"
    if [[ -n "${QEMU_EXTRA_KEY:-}" ]]; then
        cp "$QEMU_WORKDIR/inventory.ini" "$QEMU_WORKDIR/inventory-extrakey.ini"
        sed -i "s|^ansible_ssh_private_key_file=.*|ansible_ssh_private_key_file=$EXTRA_KEY|" "$QEMU_WORKDIR/inventory-extrakey.ini"
    fi
    if [[ -n "${QEMU_LUKS_PASSPHRASE:-}" ]]; then
        type_passphrase 600 > "$QEMU_WORKDIR/passphrase.log" 2>&1 &
    fi
    wait_for_ssh "$TEST_KEY" "$port" 150
}

# Runs of different envs may go in parallel, but the install targets all have a volume group vg.test: only one disk at a
# time is attached to the host. The lock is held by file descriptor 9 until the shell exits.
claim_nbd() {
    exec 9> /tmp/tuxifier-tests-nbd.lock
    flock 9
    NBD=/dev/nbd0
}

# The installed system may need SELinux in permissive mode at its first boot (see strict_selinux in the README of the
# role); tuxifier leaves the kernel arguments to the administrator. This adds enforcing=0 to the boot entries and to the
# grubenv kernelopts on /boot of the install target (partition $BOOT_PARTITION), the same as the initramfs boot has it on its command line.
permissive_first_boot() {
    local mnt console=""
    # The prompt for the passphrase of the root has to come at the serial console, see serial_args.
    [[ -z "${QEMU_LUKS_PASSPHRASE:-}" ]] || console=" console=ttyS0"
    # EL8 has no boot loader specification entries: the linux lines of its grub.cfg are patched. The function runs in sh.
    local patch="patch_grub_cfg() { [ -e \"\$1\" ] && ! grep -q enforcing=0 \"\$1\" && sed -i '/^[[:space:]]*linux/s/\$/ enforcing=0$console/' \"\$1\"; return 0; };"
    mnt="$(mktemp -d)"
    sudo modprobe nbd max_part=8
    claim_nbd
    sudo qemu-nbd -c "$NBD" "$QEMU_WORKDIR/target.qcow2"
    for _ in $(seq 1 20); do [[ -b "${NBD}p$BOOT_PARTITION" ]] && break; sleep 0.5; done
    sudo mount "${NBD}p$BOOT_PARTITION" "$mnt"
    sudo sh -c "$patch
        for f in '$mnt'/loader/entries/*.conf; do
            [ -e \"\$f\" ] && ! grep -q 'enforcing=0' \"\$f\" && sed -i '/^options /s/\$/ enforcing=0$console/' \"\$f\"
        done
        for f in '$mnt'/grub2/grubenv; do
            [ -e \"\$f\" ] && ! grep -q 'enforcing=0' \"\$f\" && sed -i '/^kernelopts=/s/\$/ enforcing=0$console/' \"\$f\"
        done
        for f in '$mnt'/grub2/grub.cfg; do
            patch_grub_cfg \"\$f\"
        done
        true"
    if [[ "$FIRMWARE" == uefi ]]; then
        # EL8 keeps the whole grub.cfg on the ESP, partition 2
        local esp
        esp="$(mktemp -d)"
        sudo mount "${NBD}p2" "$esp"
        sudo sh -c "$patch for f in '$esp'/EFI/*/grub.cfg; do patch_grub_cfg \"\$f\"; done; true"
        sudo umount "$esp"
        rmdir "$esp"
    fi
    sudo umount "$mnt"
    sudo vgchange -an --devicesfile "" vg.test > /dev/null 2>&1 || true
    sudo qemu-nbd -d "$NBD" > /dev/null
    rmdir "$mnt"
}

ssh_vm() {
    local port
    port="$(sed -n 's/^ansible_port=//p' "$QEMU_WORKDIR/inventory.ini")"
    ssh -i "$TEST_KEY" -p "$port" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o BatchMode=yes -o ConnectTimeout=3 root@127.0.0.1 "$@"
}

# continue_install=true: the sshd of the initramfs goes away at the switch root and the one of the installed system
# comes up on the same forwarded port. The installed system is recognised by a root on a block device; the initramfs has a rootfs.
wait_installed() {
    echo "waiting for the installed system"
    for _ in $(seq 1 150); do
        if ssh_vm 'findmnt --noheadings --output SOURCE / | grep -q "^/dev/"' 2> /dev/null; then
            echo "installed system is up"
            return 0
        fi
        sleep 4
    done
    echo "the installed system did not come up, see $QEMU_WORKDIR/console.log" >&2
    return 1
}

poweroff_installed() {
    ssh_vm systemctl poweroff 2> /dev/null || true
    wait_poweroff 60
}

wait_poweroff() {
    local pid
    pid="$(cat "$PIDFILE")"
    for _ in $(seq 1 "${1:-150}"); do
        kill -0 "$pid" 2> /dev/null || { echo "VM has powered off"; return 0; }
        sleep 4
    done
    echo "VM did not power off in time, see $QEMU_WORKDIR/console.log" >&2
    return 1
}

start() {
    mkdir -p "$QEMU_WORKDIR"
    if [[ -s "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2> /dev/null; then
        echo "VM already running" >&2
        exit 1
    fi
    start_initramfs
}

stop() {
    if [[ -s "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        kill "$(cat "$PIDFILE")"
    fi
    rm -f "$PIDFILE" "$MONITOR_SOCK" "$SERIAL_SOCK" "$QEMU_WORKDIR/OVMF_VARS.fd"
    [[ -n "${QEMU_KEEP_DISK:-}" ]] || rm -f "$QEMU_WORKDIR/target.qcow2" "$QEMU_WORKDIR"/extra*.qcow2
}

change_vars() {
    local target url=""
    target="$(change_target_distro "$DISTRO")"
    [[ -z "${QEMU_MIRROR:-}" ]] || url="$("$TESTS_SCRIPTS_DIR/mirror-url.sh" "$QEMU_MIRROR" "$target")"
    echo "-e __test_distro=$target -e __test_repo_url=$url"
}

case "${1:-}" in
    change-vars) change_vars ;;
    start) start ;;
    restart) KEEP_DISK=1 start ;;
    wait-poweroff) wait_poweroff ;;
    permissive-first-boot) permissive_first_boot ;;
    wait-installed) wait_installed ;;
    poweroff-installed) poweroff_installed ;;
    boot-disk) boot_disk ;;
    stop) stop ;;
    *) echo "usage: $0 start|restart|change-vars|wait-poweroff|wait-installed|poweroff-installed|permissive-first-boot|boot-disk|stop" >&2; exit 2 ;;
esac
