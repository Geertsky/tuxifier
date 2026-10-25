#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Geert Geurts <geert@verweggistan.eu>
# GNU General Public License v3.0+ (see COPYING or
# https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: rpm_install

short_description: Idempotently import GPG keys and install RPMs into a root with rpm

description:
  - Installs RPM packages that are given as URLs or paths into a root such as C(/tuxifier-sysroot), without dnf.
  - Imports the GPG keys that verify the packages, but only the keys that are not yet in the keyring of the root.
  - Installs only the packages whose name is not installed yet, so a second run changes nothing.
  - Can reimport the rpm database with the rpm of the installed system when the installer
    wrote it in a format or place the installed system does not read.

version_added: "1.0.0"

author:
  - Geert Geurts (@Geertsky)

options:
  root:
    description:
      - Directory that is used as the root of the rpm commands, passed as C(--root).
      - The module must be able to see this directory, for example from the mount namespace of the installation.
    type: path
    default: /

  macros:
    description:
      - RPM macros to define for every rpm command, as C(--define "name value") pairs.
      - For example V(_dbpath), V(_var), V(_tmppath) or V(__urlhelpercmd).
    type: dict
    default: {}

  gpg_keys:
    description:
      - ASCII armored OpenPGP public keys, the keys themselves and not paths.
      - A key is imported when one of its fingerprints is missing from the keyring.
      - Only OpenPGP version 4 keys are supported.
    type: list
    elements: str
    default: []

  packages:
    description:
      - The packages that must be installed.
      - Presence is decided by package name. A package of which another version is installed counts as installed.
    type: list
    elements: dict
    default: []
    suboptions:
      name:
        description:
          - Name of the package as it is known to rpm once installed.
        type: str
        required: true
      url:
        description:
          - URL or path that is passed to C(rpm --install).
        type: str
        required: true
        aliases: [source]

  installed_packages:
    description:
      - Names of the packages that are installed in O(root), for example from the C(packages) of C(package_facts) run in the chroot.
      - When given, the module does not query rpm for the installed packages to decide which packages are missing.
      - Presence is decided by package name, like for O(packages).
    type: list
    elements: str

  reimport_rpmdb:
    description:
      - Make the rpm database use the database backend of the rpm of the installed system.
      - The rpm of the installer writes a sqlite database. When the rpm of the installed system uses another
        backend, for example bdb on version 8 of RHEL and its derivatives, the database is exported with
        C(rpmdb --exportdb) and imported with C(rpmdb --importdb) in a C(chroot) of O(root).
      - The old database files are moved away for the import and removed after it, when the installed system lists
        the same packages. Otherwise the old files are moved back and the module fails.
      - Nothing is done when the database is not a sqlite database or when the installed system uses sqlite.
    type: bool
    default: false

  dbpath:
    description:
      - Directory below O(root) with the database files that are replaced by O(reimport_rpmdb).
      - Defaults to the value of the V(_dbpath) macro in O(macros), and to V(/var/lib/rpm) without it.
      - Not the location that rpm is queried with, that is set with the V(_dbpath) macro.
    type: path

notes:
  - The fingerprints of the keys are computed by the module, C(gpg) is not required.
  - O(reimport_rpmdb) needs C(chroot) and the C(rpm) and C(rpmdb) of the installed system inside O(root), which the installed packages provide.

attributes:
  check_mode:
    support: full
    description:
      - Reports what would be imported and installed without running a command that changes anything.
  diff_mode:
    support: none
    description:
      - Does not provide a diff.
  platform:
    support: full
    platforms: posix
    description:
      - Runs on POSIX systems with the rpm tools.

requirements:
  - C(rpm) and C(rpmkeys)
  - C(chroot), only with O(reimport_rpmdb)
"""

EXAMPLES = r"""
---
- name: Import the distribution key and install the minimal package set into the sysroot
  geertsky.tuxifier.rpm_install:
    root: /tuxifier-sysroot
    macros:
      _dbpath: /var/lib/rpm
      _var: /var
      _tmppath: /var/tmp
    gpg_keys:
      - "{{ lookup('ansible.builtin.file', gpg_key) }}"
    packages: "{{ generate_minimal_install.packages }}"
    reimport_rpmdb: "{{ rpmdb_reimport }}"
  notify: Relabel sysroot

- name: Only make sure a key is imported
  geertsky.tuxifier.rpm_install:
    root: /tuxifier-sysroot
    gpg_keys:
      - "{{ lookup('ansible.builtin.file', gpg_key) }}"
"""

RETURN = r"""
---
keys_imported:
  description:
    - Upper-case fingerprints of the keys that were imported, or would be in check mode.
  returned: always
  type: list
  elements: str
  sample: [21CB256AE16FC54C6E652949702D426D350D275D]

packages_installed:
  description:
    - Names of the packages that were installed, or would be in check mode.
  returned: always
  type: list
  elements: str
  sample: [bash, coreutils]

packages_present:
  description:
    - Names of the requested packages that were installed before this run.
  returned: always
  type: list
  elements: str
  sample: [glibc]

rpmdb_reimported:
  description:
    - Whether the rpm database was reimported, or would be in check mode.
  returned: always
  type: bool
  sample: false
"""

import os
import shutil
import tempfile

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.geertsky.tuxifier.plugins.module_utils.rpm_utils import (
    PUBKEY_PACKAGE,
    RpmRunner,
    key_fingerprints,
    missing_packages,
)

CHROOT_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"
SQLITE_DATABASE = "rpmdb.sqlite"


class ChrootRunner(object):
    """Run the commands of the installed system in a chroot of the root."""

    def __init__(self, module, root):
        self.module = module
        self.chroot = [module.get_bin_path("chroot", required=True), root]

    def run(self, *args, **kwargs):
        """Return ``(command, rc, stdout, stderr)`` with stdin and stdout as bytes."""
        command = self.chroot + list(args)
        rc, stdout, stderr = self.module.run_command(
            command,
            data=kwargs.get("data"),
            binary_data=True,
            encoding=None,
            environ_update=dict(PATH=CHROOT_PATH),
        )
        return command, rc, stdout, stderr

    def installed_names(self):
        """Return the names of the packages that the rpm of the installed system lists."""
        command, rc, stdout, stderr = self.run("rpm", "-qa", "--queryformat", "%{NAME}\\n")
        if rc != 0:
            self.module.fail_json(msg="rpm -qa failed in the root", cmd=command, rc=rc, stderr=stderr)
        return stdout.decode("utf-8").split()

    def database_backend(self):
        """Return the database backend that the rpm of the installed system uses."""
        command, rc, stdout, stderr = self.run("rpm", "--eval", "%{_db_backend}")
        if rc != 0:
            self.module.fail_json(msg="rpm --eval failed in the root", cmd=command, rc=rc, stderr=stderr)
        return stdout.decode("utf-8").strip()


def database_files(directory):
    """Return the rpmdb files in ``directory``."""
    if not os.path.isdir(directory):
        return []
    return sorted(
        os.path.join(directory, name)
        for name in os.listdir(directory)
        if name.startswith("rpmdb")
    )


def move_files(files, destination):
    """Move ``files`` into ``destination`` and return their new paths."""
    moved = []
    for path in files:
        target = os.path.join(destination, os.path.basename(path))
        shutil.move(path, target)
        moved.append(target)
    return moved


def reimport_needed(chroot_runner, directory):
    """Return whether ``directory`` holds a sqlite database while the installed system uses another backend."""
    if not os.path.exists(os.path.join(directory, SQLITE_DATABASE)):
        return False
    return chroot_runner.database_backend() != "sqlite"


def reimport_database(module, runner, chroot_runner, directory):
    """Export the database, move its files away and import it with the rpm of the installed system.

    The old files are moved back when the import fails or when the installed system does not list
    the same packages afterwards.
    """
    expected = sorted(set(runner.installed_names()) - set([PUBKEY_PACKAGE]))

    command, rc, exported, stderr = chroot_runner.run("rpmdb", "--exportdb")
    if rc != 0:
        module.fail_json(msg="rpmdb --exportdb failed", cmd=command, rc=rc, stderr=stderr)

    backup = tempfile.mkdtemp(prefix="rpmdb-reimport-", dir=os.path.join(runner.root, "var", "tmp"))
    try:
        moved = move_files(database_files(directory), backup)
    except (IOError, OSError) as exc:
        module.fail_json(msg="Unable to move the database files away: %s" % exc, dbpath=directory)

    def restore(message, **details):
        for path in database_files(directory):
            os.remove(path)
        move_files(moved, directory)
        module.fail_json(msg=message, backup=backup, **details)

    command, rc, _stdout, stderr = chroot_runner.run("rpmdb", "--importdb", data=exported)
    if rc != 0:
        restore("rpmdb --importdb failed, the old database was restored", cmd=command, rc=rc, stderr=stderr)

    imported = sorted(set(chroot_runner.installed_names()) - set([PUBKEY_PACKAGE]))
    if imported != expected:
        restore("The reimported database does not list the installed packages, the old database was restored")
    shutil.rmtree(backup)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            root=dict(type="path", default="/"),
            macros=dict(type="dict", default={}),
            gpg_keys=dict(type="list", elements="str", default=[], no_log=False),
            packages=dict(
                type="list",
                elements="dict",
                default=[],
                options=dict(
                    name=dict(type="str", required=True),
                    url=dict(type="str", required=True, aliases=["source"]),
                ),
            ),
            installed_packages=dict(type="list", elements="str"),
            reimport_rpmdb=dict(type="bool", default=False),
            dbpath=dict(type="path"),
        ),
        supports_check_mode=True,
    )
    params = module.params
    runner = RpmRunner(module, params["root"], params["macros"])

    parsed_keys = []
    for key in params["gpg_keys"]:
        try:
            parsed_keys.append((key, key_fingerprints(key)))
        except ValueError as exc:
            module.fail_json(msg="Unable to read gpg_keys: %s" % exc)

    imported = set(runner.imported_fingerprints())
    keys_to_import = [(key, fingerprints) for key, fingerprints in parsed_keys if not imported.issuperset(fingerprints)]
    keys_imported = sorted({fingerprint for _key, fingerprints in keys_to_import for fingerprint in fingerprints} - imported)

    installed_before = params["installed_packages"]
    if installed_before is None:
        installed_before = runner.installed_names()
    packages = params["packages"]
    to_install = missing_packages(packages, installed_before)
    names_to_install = [package["name"] for package in to_install]
    present = sorted({package["name"] for package in packages} - set(names_to_install))

    if not module.check_mode:
        for key, _fingerprints in keys_to_import:
            runner.run("rpmkeys", "--import", "/dev/stdin", data=key)
        if to_install:
            runner.run("rpm", "--install", *[package["url"] for package in to_install])

    reimport = False
    if params["reimport_rpmdb"]:
        directory = os.path.join(
            params["root"], (params["dbpath"] or params["macros"].get("_dbpath", "/var/lib/rpm")).lstrip(os.sep))
        chroot_runner = ChrootRunner(module, params["root"])
        if module.check_mode and to_install:
            reimport = True
        elif not module.check_mode or os.path.exists(os.path.join(params["root"], "usr", "bin", "rpm")):
            reimport = reimport_needed(chroot_runner, directory)
        if reimport and not module.check_mode:
            reimport_database(module, runner, chroot_runner, directory)

    module.exit_json(
        changed=bool(keys_imported or to_install or reimport),
        keys_imported=keys_imported,
        packages_installed=names_to_install,
        packages_present=present,
        rpmdb_reimported=reimport,
    )


if __name__ == "__main__":
    main()
