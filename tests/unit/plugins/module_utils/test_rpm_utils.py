# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

import os

import pytest

from ansible_collections.geertsky.tuxifier.plugins.module_utils import rpm_utils

__metaclass__ = type

KEY_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "roles", "ansible_tuxifier", "files", "etc", "pki", "rpm-gpg")


def read_key(name):
    with open(os.path.join(KEY_DIR, name)) as handle:
        return handle.read()


def test_key_fingerprints_of_the_rocky_9_key():
    assert rpm_utils.key_fingerprints(read_key("RPM-GPG-KEY-Rocky-9")) == ["21CB256AE16FC54C6E652949702D426D350D275D"]


def test_key_fingerprints_returns_every_primary_key_of_a_file():
    assert len(rpm_utils.key_fingerprints(read_key("RPM-GPG-KEY-openSUSE-Leap-16.0"))) == 2


def test_key_fingerprints_cover_only_primary_keys():
    # Subkeys have their own fingerprints, which rpmkeys --list does not show.
    assert len(rpm_utils.key_fingerprints(read_key("RPM-GPG-KEY-AlmaLinux-9"))) == 1


def test_key_fingerprints_reject_text_without_a_key():
    with pytest.raises(ValueError):
        rpm_utils.key_fingerprints("not a key")


def test_parse_key_list_uppercases_and_skips_other_lines():
    output = "21cb256ae16fc54c6e652949702d426d350d275d Rocky key public key\nnoise\n"
    assert rpm_utils.parse_key_list(output) == ["21CB256AE16FC54C6E652949702D426D350D275D"]


def test_missing_packages_keeps_order_and_skips_installed_and_duplicate_urls():
    requested = [
        dict(name="b", url="http://x/b.rpm"),
        dict(name="a", url="http://x/a.rpm"),
        dict(name="c", url="http://x/c.rpm"),
        dict(name="c2", url="http://x/c.rpm"),
    ]
    assert rpm_utils.missing_packages(requested, ["a"]) == [requested[0], requested[2]]


class FakeModule(object):
    def get_bin_path(self, name, required=False):
        return "/opt/bin/" + name


def test_argv_puts_root_and_sorted_macros_before_the_arguments():
    runner = rpm_utils.RpmRunner(FakeModule(), "/sysroot", {"b": "2 two", "a": "1"})
    assert runner.argv("rpm", "-qa") == [
        "/opt/bin/rpm", "--root", "/sysroot", "--define", "a 1", "--define", "b 2 two", "-qa"]


def test_argv_without_root_has_no_root_option():
    assert rpm_utils.RpmRunner(FakeModule()).argv("rpmkeys", "--list") == ["/opt/bin/rpmkeys", "--list"]
