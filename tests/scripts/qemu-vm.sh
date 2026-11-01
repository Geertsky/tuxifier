#!/usr/bin/env bash
# SPDX-License-Identifier: EUPL-1.2
# Start and stop the throwaway qemu VM of the tox envs "qemu-rocky{8,9,10}", booted from the incubator initramfs.
#
#   qemu-vm.sh start          boot the initramfs of QEMU_DISTRO on an empty install target (/dev/vda) and write
#                             $QEMU_WORKDIR/inventory.ini; ansible uses the python of python-nest
#   qemu-vm.sh restart        the same, on the install target the previous run left (the VM has powered off)
#   qemu-vm.sh wait-poweroff  wait until the VM has powered off (the initramfs does that after a finished install)
#   qemu-vm.sh permissive-first-boot  add enforcing=0 to the boot entries of the powered off install target (sudo)
#   qemu-vm.sh boot-disk      boot the installed system from the install target; ansible uses the system python
#   qemu-vm.sh stop           power the VM off and remove its disk (QEMU_KEEP_DISK=1 keeps it)
#
# Environment:
#   QEMU_WORKDIR      directory for the disks, key, pid file and inventory (required)
#   QEMU_DISTRO       rocky8, rocky9 or rocky10 (default: rocky9)
#   QEMU_SCRATCH_SIZE size of the install target disk (default: 8G)
#   QEMU_MEMORY       memory in MiB (default: 3072)
# The initramfs images are built by initramfs.sh; see common.sh for the directories it uses.
set -euo pipefail
# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

: "${QEMU_WORKDIR:?QEMU_WORKDIR must be set}"
SCRATCH_SIZE="${QEMU_SCRATCH_SIZE:-8G}"
MEMORY="${QEMU_MEMORY:-3072}"
DISTRO="${QEMU_DISTRO:-rocky9}"
PIDFILE="$QEMU_WORKDIR/qemu.pid"

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
    if [[ -S "$QEMU_WORKDIR/monitor.sock" ]]; then
        echo "screendump $QEMU_WORKDIR/screen.ppm" | python3 -c '
import socket, sys
s = socket.socket(socket.AF_UNIX)
s.connect(sys.argv[1])
s.sendall(sys.stdin.read().encode() + b"\n")
' "$QEMU_WORKDIR/monitor.sock" || true
        sleep 1
        echo "screen of the VM: $QEMU_WORKDIR/screen.ppm" >&2
    fi
    return 1
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
    eval "$("$TESTS_SCRIPTS_DIR/initramfs.sh" "$DISTRO" | grep -E '^(kernel|initrd)=')"
    kernel="$kernel"
    initrd="$initrd"
    [[ -n "${KEEP_DISK:-}" ]] || qemu-img create -q -f qcow2 "$QEMU_WORKDIR/target.qcow2" "$SCRATCH_SIZE"
    port="$(free_port)"
    qemu-system-x86_64 -enable-kvm -cpu host -smp 2 -m "$MEMORY" -display none -daemonize \
        -pidfile "$PIDFILE" -serial "file:$QEMU_WORKDIR/console.log" \
        -kernel "$kernel" -initrd "$initrd" \
        -append "rd.neednet=1 ip=dhcp root=LABEL=root enforcing=0 console=ttyS0" \
        -drive "file=$QEMU_WORKDIR/target.qcow2,if=virtio,format=qcow2" \
        -nic "user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:$port-:22"
    write_inventory "$TEST_KEY" "$port" "ansible_python_interpreter=/local/conda/envs/python-nest/bin/python3"
    wait_for_ssh "$TEST_KEY" "$port" 60
}

boot_disk() {
    local port
    [[ -s "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2> /dev/null && { echo "VM still running" >&2; exit 1; }
    port="$(free_port)"
    qemu-system-x86_64 -enable-kvm -cpu host -smp 2 -m "$MEMORY" -display none -daemonize \
        -pidfile "$PIDFILE" -serial "file:$QEMU_WORKDIR/console.log" \
        -monitor "unix:$QEMU_WORKDIR/monitor.sock,server,nowait" \
        -drive "file=$QEMU_WORKDIR/target.qcow2,if=virtio,format=qcow2" \
        -nic "user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:$port-:22"
    write_inventory "$TEST_KEY" "$port"
    wait_for_ssh "$TEST_KEY" "$port" 150
}

# The installed system may need SELinux in permissive mode at its first boot (see strict_selinux in the README of the
# role); tuxifier leaves the kernel arguments to the administrator. This adds enforcing=0 to the boot entries and to the
# grubenv kernelopts on /boot of the install target (partition 2), the same as the initramfs boot has it on its command line.
permissive_first_boot() {
    local mnt
    mnt="$(mktemp -d)"
    sudo modprobe nbd max_part=8
    sudo qemu-nbd -c /dev/nbd0 "$QEMU_WORKDIR/target.qcow2"
    for _ in $(seq 1 20); do [[ -b /dev/nbd0p2 ]] && break; sleep 0.5; done
    sudo mount /dev/nbd0p2 "$mnt"
    sudo sh -c "
        for f in '$mnt'/loader/entries/*.conf; do
            [ -e \"\$f\" ] && ! grep -q 'enforcing=0' \"\$f\" && sed -i '/^options /s/\$/ enforcing=0/' \"\$f\"
        done
        for f in '$mnt'/grub2/grubenv; do
            [ -e \"\$f\" ] && ! grep -q 'enforcing=0' \"\$f\" && sed -i '/^kernelopts=/s/\$/ enforcing=0/' \"\$f\"
        done
        true"
    sudo umount "$mnt"
    sudo vgchange -an --devicesfile "" vg.test > /dev/null 2>&1 || true
    sudo qemu-nbd -d /dev/nbd0 > /dev/null
    rmdir "$mnt"
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
    rm -f "$PIDFILE" "$QEMU_WORKDIR/monitor.sock"
    [[ -n "${QEMU_KEEP_DISK:-}" ]] || rm -f "$QEMU_WORKDIR/target.qcow2"
}

case "${1:-}" in
    start) start ;;
    restart) KEEP_DISK=1 start ;;
    wait-poweroff) wait_poweroff ;;
    permissive-first-boot) permissive_first_boot ;;
    boot-disk) boot_disk ;;
    stop) stop ;;
    *) echo "usage: $0 start|restart|wait-poweroff|permissive-first-boot|boot-disk|stop" >&2; exit 2 ;;
esac
