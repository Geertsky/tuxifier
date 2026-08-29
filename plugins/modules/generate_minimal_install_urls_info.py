#!/usr/bin/python3
# -*- coding: utf-8 -*-

# Copyright: (c) 2023, Geert Geurts <geert@verweggistan.eu>
# GNU General Public License v3.0+ (see COPYING or
# https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

import tempfile
import traceback
from pathlib import Path

from ansible.module_utils.basic import AnsibleModule


__metaclass__ = type

VALID_REPO_URL_TYPES = ("metalink", "mirrorlist", "baseurl")
GROUP_PACKAGE_TYPES = ("mandatory", "default")


DOCUMENTATION = r"""
---
module: generate_minimal_install_urls_info

short_description: Resolve RPM URLs for a minimal distribution installation

description:
  - Uses the Python DNF API to resolve packages, package groups, and dependencies.
  - Resolves against only the repository supplied in the distribution parameter.
  - Returns both a whitespace-separated URL string and a URL list.

author:
  - Geert Geurts (@Geertsky)

version_added: "1.0.0"

options:
  rpmdb_reimport:
    description:
      - Makes it possible for the rpmdb to be reimported.
    required: false
    default: false
    type: bool

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
          - Group specifications must start with C(@), for example C(@Core).
        required: true
        type: list
        elements: str
      pre_pivot_cmds:
        description:
          - Commands that should be issued after minimal install to make the installation ansible capable
        required: false
        type: list
        elements: str
"""

EXAMPLES = r"""
---
- name: Resolve URLs for a Rocky Linux minimal installation
  geertsky.bambini.generate_minimal_install_urls_info:
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
      pre_pivot_cmds:
        - "dnf install -y python3.12"
  register: result

- name: Show resolved URLs
  ansible.builtin.debug:
    var: result.urls
"""

RETURN = r"""
---
rpm_urls:
  description:
    - All resolved RPM URLs as one whitespace-separated string.
  returned: always
  type: str

urls:
  description:
    - All resolved RPM URLs as a list.
  returned: always
  type: list
  elements: str

package_count:
  description:
    - Number of RPM URLs returned.
  returned: always
  type: int
"""


def generate_urls(distribution):
    """Resolve package/group specifications and return their RPM URLs."""
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
                url = package.remote_location()
                if not url:
                    raise RuntimeError(
                        "DNF did not provide a remote URL for package {0}".format(
                            package
                        )
                    )
                urls.append(url)

    # Preserve order while removing accidental duplicates.
    return list(dict.fromkeys(urls))


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
                "pre_pivot_cmds": {
                    "type": "list",
                    "elements": "str",
                    "required": False,
                },
            },
        },
        "rpmdb_reimport": {
            "type": "bool",
            "required": False,
            "default": False,
        },
    }

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
    )

    try:
        urls = generate_urls(module.params["distribution"])
    except Exception as exc:
        module.fail_json(
            msg=str(exc),
            exception=traceback.format_exc(),
        )

    module.exit_json(
        changed=False,
        rpm_urls=" ".join(urls),
        urls=urls,
        package_count=len(urls),
    )


def main():
    run_module()


if __name__ == "__main__":
    main()
