#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2023, Geert Geurts <geert@verweggistan.eu>
# European Union Public Licence v. 1.2 (see LICENSE or
# https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12)

from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""
---
module: generate_minimal_install_info

short_description: Resolve the RPM packages for a minimal distribution installation

description:
  - Uses the Python DNF API to resolve packages, package groups, and dependencies.
  - Resolves against only the repository supplied in the distribution parameter.
  - Returns the resolved packages as a list of dicts with the name and the URL of every package, and the URLs as one whitespace-separated string.

author:
  - Geert Geurts (@Geertsky)

version_added: "1.0.0"

options:
  distribution:
    description:
      - Distribution and repository definition.
    required: true
    type: dict
    suboptions:
      name:
        description:
          - Distribution name.
        required: true
        type: str
      version:
        description:
          - Distribution release version used for DNF substitutions.
        required: true
        type: str
      arch:
        description:
          - Target architecture used for DNF substitutions.
        required: true
        type: str
      efi_vendor_dir:
        description:
          - Directory below EFI/ on the ESP that holds the boot loader of the distribution.
          - Not used by this module; accepted so the complete distribution dict can be passed.
        required: false
        type: str
      efi_loader:
        description:
          - File name of the shim EFI binary in O(distribution.efi_vendor_dir).
          - Not used by this module; accepted so the complete distribution dict can be passed.
        required: false
        type: str
      grub_cfg:
        description:
          - Path of the grub configuration file that is read at boot.
          - Not used by this module; accepted so the complete distribution dict can be passed.
        required: false
        type: str
      repo:
        description:
          - Repository definition.
        required: true
        type: dict
        suboptions:
          type:
            description:
              - Repository URL type.
            required: true
            type: str
            choices:
              - metalink
              - mirrorlist
              - baseurl
          url:
            description:
              - Repository URL.
            required: true
            type: str
      minimalpackages:
        description:
          - Package specifications and DNF groups to resolve.
          - Group specifications must start with "@", for example "@Core".
        required: true
        type: list
        elements: str

notes:
  - Runs where the Python dnf module is available. The role delegates it to C(localhost), the Ansible controller,
    with C(/usr/bin/python3) as interpreter, so the controller needs python3-dnf. It does not run in the initramfs.
  - Needs network access to the repository, but does not change the host it runs on.

requirements:
  - Python C(dnf) module (python3-dnf)
"""

EXAMPLES = r"""
---
- name: Resolve the packages for a Rocky Linux minimal installation
  geertsky.tuxifier.generate_minimal_install_info:
    distribution:
      name: rocky
      version: "10"
      arch: x86_64
      repo:
        type: baseurl
        url: https://mirror.example.org/rockylinux/10/BaseOS/x86_64/os/
      minimalpackages:
        - "@Core"
        - kernel
        - lvm2
  register: result

- name: Show the resolved packages
  ansible.builtin.debug:
    var: result.packages
"""

RETURN = r"""
---
rpm_urls:
  description:
    - All resolved RPM URLs as one whitespace-separated string.
  returned: always
  type: str

packages:
  description:
    - All resolved RPMs as a list of dicts, sorted by package.
  returned: always
  type: list
  elements: dict
  contains:
    name:
      description: Name of the package.
      type: str
    url:
      description: URL of the RPM.
      type: str

package_count:
  description:
    - Number of packages returned.
  returned: always
  type: int
"""


import tempfile
import traceback
from pathlib import Path

from ansible.module_utils.basic import AnsibleModule

VALID_REPO_URL_TYPES = ("metalink", "mirrorlist", "baseurl")
GROUP_PACKAGE_TYPES = ("mandatory", "default")


def generate_packages(distribution):
    """Resolve package/group specifications and return the name and URL of every package."""
    try:
        import dnf
    except ImportError as exc:
        raise RuntimeError(
            "the Python dnf module is required on the host executing this module"
        ) from exc

    repo_type = distribution["repo"]["type"]
    repo_url = distribution["repo"]["url"]
    releasever = str(distribution["version"])
    arch = distribution["arch"]
    package_specs = distribution["minimalpackages"]

    cleaned_specs = [
        package_spec.strip()
        for package_spec in package_specs
        if package_spec and package_spec.strip()
    ]
    if not cleaned_specs:
        raise ValueError(
            "distribution.minimalpackages must contain at least one package "
            "or @group"
        )

    with tempfile.TemporaryDirectory(prefix="dnf-url-resolver-") as temp_dir:
        workdir = Path(temp_dir)
        reposdir = workdir / "repos"
        installroot = workdir / "root"
        cachedir = workdir / "cache"
        logdir = workdir / "log"
        persistdir = workdir / "persist"

        for directory in (
            reposdir,
            installroot,
            cachedir,
            logdir,
            persistdir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        with dnf.Base() as base:
            conf = base.conf
            conf.reposdir = [str(reposdir)]
            conf.installroot = str(installroot)
            conf.cachedir = str(cachedir)
            conf.logdir = str(logdir)
            conf.persistdir = str(persistdir)

            conf.substitutions["releasever"] = str(distribution["version"])
            conf.substitutions["arch"] = str(distribution["arch"])
            conf.substitutions["basearch"] = str(distribution["arch"])

            repo_type = str(distribution["repo"]["type"]).strip().lower()
            repo_url = str(distribution["repo"]["url"]).strip()

            # Required for dependencies expressed as absolute file paths. Eg. alma8 shim/grub dependencies
            optional_metadata_types = set(conf.optional_metadata_types)
            optional_metadata_types.add("filelists")
            conf.optional_metadata_types = sorted(optional_metadata_types)

            repo_id = "{}-{}".format(
                distribution["name"],
                distribution["version"],
            )

            repo = base.repos.add_new_repo(repo_id, conf)

            if repo_type == "baseurl":
                repo.baseurl = [repo_url]
            elif repo_type == "metalink":
                repo.metalink = repo_url
            elif repo_type == "mirrorlist":
                repo.mirrorlist = repo_url
            else:
                raise ValueError(
                    "Unsupported repository type {!r}; expected one of: "
                    "baseurl, metalink, mirrorlist".format(repo_type)
                )

            # Resolve as an empty target system using only the supplied repo.
            base.fill_sack(
                load_system_repo=False,
                load_available_repos=True
            )

            # Required before looking up or installing DNF package groups.
            base.read_comps(arch_filter=True)

            for package_spec in cleaned_specs:
                if package_spec.startswith("@"):
                    group_pattern = package_spec[1:].strip()
                    if not group_pattern:
                        raise ValueError(
                            "empty DNF group specification: '@'"
                        )

                    group = base.comps.group_by_pattern(
                        group_pattern,
                        case_sensitive=False
                    )
                    if group is None:
                        available_groups = ", ".join(
                            sorted(
                                group_item.id
                                for group_item in base.comps.groups
                            )
                        )
                        raise ValueError(
                            "DNF group {0!r} was not found. "
                            "Available group IDs: {1}".format(
                                package_spec,
                                available_groups or "<none>"
                            )
                        )

                    base.group_install(
                        group.id,
                        GROUP_PACKAGE_TYPES,
                        strict=True
                    )
                else:
                    base.install(
                        package_spec,
                        reponame=repo_id,
                        strict=True
                    )

            base.resolve()

            transaction_packages = sorted(
                base.transaction.install_set,
                key=lambda package: (
                    package.name,
                    package.epoch,
                    package.version,
                    package.release,
                    package.arch,
                )
            )

            urls = []
            for package in transaction_packages:
                name = package.name
                url = package.remote_location()
                if not url:
                    raise RuntimeError(
                        "DNF did not provide a remote URL for package {0}".format(
                            package
                        )
                    )
                urls.append({"name": name, "url": url})

    # Preserve order while removing accidental duplicates.
    return list({u["url"]: u for u in urls}.values())


def run_module():
    module_args = {
        "distribution": {
            "type": "dict",
            "required": True,
            "options": {
                "name": {
                    "type": "str",
                    "required": True,
                },
                "version": {
                    "type": "str",
                    "required": True,
                },
                "arch": {
                    "type": "str",
                    "required": True,
                },
                "efi_vendor_dir": {
                    "type": "str",
                    "required": False,
                },
                "efi_loader": {
                    "type": "str",
                    "required": False,
                },
                "grub_cfg": {
                    "type": "str",
                    "required": False,
                },
                "repo": {
                    "type": "dict",
                    "required": True,
                    "options": {
                        "type": {
                            "type": "str",
                            "required": True,
                            "choices": list(VALID_REPO_URL_TYPES),
                        },
                        "url": {
                            "type": "str",
                            "required": True,
                        },
                    },
                },
                "minimalpackages": {
                    "type": "list",
                    "elements": "str",
                    "required": True,
                },
            },
        },
    }

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
    )

    try:
        packages = generate_packages(module.params["distribution"])
    except Exception as exc:
        module.fail_json(
            msg=str(exc),
            exception=traceback.format_exc(),
        )

    module.exit_json(
        changed=False,
        rpm_urls=" ".join(package["url"] for package in packages),
        packages=packages,
        package_count=len(packages),
    )


def main():
    run_module()


if __name__ == "__main__":
    main()
