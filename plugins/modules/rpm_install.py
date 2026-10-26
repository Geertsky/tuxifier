#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Geert Geurts <geert@verweggistan.eu>
# European Union Public Licence v. 1.2 (see LICENSE or
# https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12)

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

notes:
  - The fingerprints of the keys are computed by the module, C(gpg) is not required.

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
"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.geertsky.tuxifier.plugins.module_utils.rpm_utils import (
    RpmRunner,
    key_fingerprints,
    missing_packages,
)

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

    module.exit_json(
        changed=bool(keys_imported or to_install),
        keys_imported=keys_imported,
        packages_installed=names_to_install,
        packages_present=present,
    )


if __name__ == "__main__":
    main()
