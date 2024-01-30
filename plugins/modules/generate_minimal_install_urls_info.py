#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2023, Geert Geurts <geert@verweggistan.eu>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
import os
import shutil
import atexit
import dnf
from ansible.module_utils.basic import AnsibleModule

__metaclass__ = type

DOCUMENTATION = r'''
module: generate_minimal_install_urls

short_description: "This module generates urls to all the rpms needed for a minimal install of a distribution of choice."

description:
    - This module uses the dnf module to generate urls for all rpms required for installation of a set of packages and/or package groups.
    - The output is a string containing all the urls to the required rpms.

author:
    - Geert Geurts (@Geertsky)

version_added: "1.0.0"

options:
    rpmdb_reimport:
        description:
            - Boolean to specify if the distribution to install uses a different location for the rpmdb as the distribution used for generating the initramfs.
                    (See <a href="https://fedoraproject.org/wiki/Changes/RelocateRPMToUsr">Fedora Wiki RelocateRPMToUsr</a>)
        required: False
        default: False
        type: bool
    distribution:
        description:
            - Dictionary to define the distribution to install.
        required: True
        type: dict
        suboptions:
            arch:
                description:
                    - The architecture for the distribution to install.
                required: True
                type: str
            name:
                description:
                    - The name of the distribution.
                required: True
                type: str
            version:
                description:
                    - The version of the distribution to install.
                required: True
                type: str
            repo:
                description:
                    - Dictionary to define the repository to use for the installation.
                required: True
                type: dict
                suboptions:
                    type:
                        description:
                            - The type of the link specified by the url option. One of [metalink|mirrorlist|baseurl].
                        required: True
                        type: str
                    url:
                        description:
                            - The url of the repository.
                        required: True
                        type: str
'''

EXAMPLES = r'''
---
- name: Retrieve urls
    geertsky.generate_minimal_install_urls:
        rpmdb_reimport: True
        distribution:
            name: "rocky"
            version: 8
            repo:
                type: "metalink"
                url: "https://mirrors.rockylinux.org/metalink?arch=$basearch&repo=BaseOS-$releasever"
            minimalpackages:
                - "@Core"
                - "kernel"
    register: result

- ansible.builtin.debug:
    var: result.rpm_urls
'''

RETURN = r'''
---
rpm_urls:
    description:
        - The module returns one large string with urls to all the rpms needed to resolve the minimalpackages.
    type: str
    returned: always
    sample: >-
        http://dl.rockylinux.org/$contentdir/$releasever/BaseOS/$basearch/os/Packages/n/NetworkManager-1.40.16-9.el8.x86_64.rpm
        http://dl.rockylinux.org/$contentdir/$releasever/BaseOS/$basearch/os/Packages/n/NetworkManager-libnm-1.40.16-9.el8.x86_64.rpm
        ...

        http://dl.rockylinux.org/$contentdir/$releasever/BaseOS/$basearch/os/Packages/y/yum-4.7.0-19.el8.noarch.rpm
        http://dl.rockylinux.org/$contentdir/$releasever/BaseOS/$basearch/os/Packages/z/zlib-1.2.11-25.el8.x86_64.rpm
'''


def run_module():
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
        distribution=dict(type="dict", required=True),
        rpmdb_reimport=dict(type="bool", required=False, default=False),
    )

    result = dict(
        changed=False,
        rpm_urls=None,
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    if module.check_mode:
        module.exit_json(**result)

    def cleanup():
        for d in ["/tmp/reposdir", "/tmp/root"]:
            try:
                shutil.rmtree(d)
            except FileNotFoundError:
                continue

    # Create tempory directories
    for d in ["/tmp/reposdir", "/tmp/root"]:
        try:
            os.mkdir(d)
        except FileExistsError:
            continue

    # Cleanup temporary directories
    atexit.register(cleanup)

    base = dnf.Base()
    conf = base.conf

    # Set the distribution vars
    conf.set_or_append_opt_value("reposdir", "/tmp/reposdir")
    conf.set_or_append_opt_value("installroot", "/tmp/root")
    conf.substitutions["releasever"] = module.params["distribution"]["version"]
    conf.substitutions["arch"] = module.params["distribution"]["arch"]
    conf.substitutions["basearch"] = module.params["distribution"]["arch"]
    if module.params["distribution"]["repo"]["type"] == "metalink":
        base.repos.add_new_repo(
            "BaseOS", conf, metalink=module.params["distribution"]["repo"]["url"]
        )
    elif module.params["distribution"]["repo"]["type"] == "mirrorlist":
        base.repos.add_new_repo(
            "BaseOS", conf, mirrorlist=module.params["distribution"]["repo"]["url"]
        )
    elif module.params["distribution"]["repo"]["type"] == "baseurl":
        base.repos.add_new_repo(
            "BaseOS", conf, baseurl=module.params["distribution"]["repo"]["url"]
        )
    base.read_all_repos()
    base.fill_sack()
    base.read_comps(arch_filter=True)
    for package in module.params["distribution"]["minimalpackages"]:
        if package[0] == "@":
            group = base.comps.group_by_pattern(package[1:])
            base.group_install(group.id, ["mandatory", "default"])
        else:
            base.install(package)
    base.resolve()

    def get_remote_location(pkg):
        return pkg.remote_location()

    urls = map(get_remote_location, list(base.transaction.install_set))

    result["rpm_urls"] = " ".join(list(urls))

    module.exit_json(**result)


def main():
    run_module()


if __name__ == "__main__":
    main()
