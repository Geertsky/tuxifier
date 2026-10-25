# -*- coding: utf-8 -*-
# SPDX-License-Identifier: EUPL-1.2

from __future__ import absolute_import, division, print_function

import os

import pytest

from ansible.module_utils import basic
from ansible.module_utils.testing import patch_module_args
from ansible_collections.geertsky.tuxifier.plugins.modules import rpm_install

__metaclass__ = type

KEY_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "roles", "ansible_tuxifier", "files", "etc", "pki", "rpm-gpg",
    "RPM-GPG-KEY-Rocky-9")
FINGERPRINT = "21CB256AE16FC54C6E652949702D426D350D275D"


class Exit(Exception):
    def __init__(self, kwargs):
        super(Exit, self).__init__(kwargs)
        self.kwargs = kwargs


@pytest.fixture
def key():
    with open(KEY_FILE) as handle:
        return handle.read()


@pytest.fixture
def run_module(monkeypatch):
    def run(args, outputs):
        """Run main(). ``outputs`` maps a command name to a list of (rc, stdout, stderr) results."""
        calls = []

        def fake_run_command(self, command, **kwargs):
            name = os.path.basename(command[0])
            if name == "chroot":
                name = "chroot-" + command[2]
            calls.append((name, command, kwargs.get("data")))
            return outputs[name].pop(0)

        def exit_json(self, **kwargs):
            raise Exit(kwargs)

        def fail_json(self, **kwargs):
            raise Exit(dict(kwargs, failed=True))

        monkeypatch.setattr(basic.AnsibleModule, "run_command", fake_run_command)
        monkeypatch.setattr(basic.AnsibleModule, "get_bin_path", lambda self, name, required=False: "/usr/bin/" + name)
        monkeypatch.setattr(basic.AnsibleModule, "exit_json", exit_json)
        monkeypatch.setattr(basic.AnsibleModule, "fail_json", fail_json)
        with patch_module_args(args), pytest.raises(Exit) as excinfo:
            rpm_install.main()
        return excinfo.value.kwargs, calls
    return run


PACKAGES = [dict(name="bash", url="http://m/bash.rpm"), dict(name="glibc", url="http://m/glibc.rpm")]


def test_second_run_changes_nothing(run_module, key):
    result, calls = run_module(
        dict(root="/sysroot", gpg_keys=[key], packages=PACKAGES),
        {"rpmkeys": [(0, FINGERPRINT.lower() + " Rocky public key\n", "")], "rpm": [(0, "bash\nglibc\n", "")]})
    assert result["changed"] is False
    assert result["packages_present"] == ["bash", "glibc"]
    assert [call[0] for call in calls] == ["rpmkeys", "rpm"]


def test_missing_key_and_packages_are_imported_and_installed_once(run_module, key, tmp_path):
    root = make_root(tmp_path)
    result, calls = run_module(
        dict(root=str(root), macros=dict(_dbpath="/var/lib/rpm"), gpg_keys=[key], packages=PACKAGES),
        {"rpmkeys": [(0, "", ""), (0, "", "")], "rpm": [(0, "glibc\n", ""), (0, "", "")]})
    assert result["changed"] is True
    assert result["keys_imported"] == [FINGERPRINT]
    assert result["packages_installed"] == ["bash"]
    import_call, install_call = calls[2], calls[3]
    assert [call[0] for call in calls] == ["rpmkeys", "rpm", "rpmkeys", "rpm"]
    assert import_call[1] == [
        "/usr/bin/rpmkeys", "--root", str(root), "--define", "_dbpath /var/lib/rpm", "--import", "/dev/stdin"]
    assert import_call[2] == key
    assert install_call[1][-2:] == ["--install", "http://m/bash.rpm"]


def test_installed_packages_replace_the_query_of_rpm(run_module):
    result, calls = run_module(
        dict(root="/sysroot", packages=PACKAGES, installed_packages=["glibc"]),
        {"rpmkeys": [(0, "", "")], "rpm": [(0, "", "")]})
    assert result["packages_installed"] == ["bash"]
    assert result["packages_present"] == ["glibc"]
    assert [call[0] for call in calls] == ["rpmkeys", "rpm"]
    assert calls[1][1][-2:] == ["--install", "http://m/bash.rpm"]


def test_check_mode_runs_no_command_that_changes_anything(run_module, key):
    result, calls = run_module(
        dict(root="/sysroot", gpg_keys=[key], packages=PACKAGES, _ansible_check_mode=True),
        {"rpmkeys": [(0, "", "")], "rpm": [(0, "", "")]})
    assert result["changed"] is True
    assert [call[0] for call in calls] == ["rpmkeys", "rpm"]


def test_url_can_be_given_as_source(run_module):
    result, _calls = run_module(
        dict(root="/sysroot", packages=[dict(name="bash", source="/srv/bash.rpm")], _ansible_check_mode=True),
        {"rpmkeys": [(0, "", "")], "rpm": [(0, "", "")]})
    assert result["packages_installed"] == ["bash"]


def test_failed_install_reports_the_command(run_module):
    result, _calls = run_module(
        dict(root="/sysroot", packages=PACKAGES),
        {"rpmkeys": [(0, "", "")], "rpm": [(0, "", ""), (1, "", "boom")]})
    assert result["failed"] is True
    assert result["rc"] == 1
    assert result["cmd"][-3:] == ["--install", "http://m/bash.rpm", "http://m/glibc.rpm"]


def test_invalid_key_fails_before_any_command(run_module):
    result, calls = run_module(dict(root="/sysroot", gpg_keys=["nonsense"]), {})
    assert result["failed"] is True
    assert calls == []


def make_root(tmp_path):
    root = tmp_path / "sysroot"
    (root / "var" / "lib" / "rpm").mkdir(parents=True)
    (root / "var" / "tmp").mkdir(parents=True)
    (root / "var" / "lib" / "rpm" / "rpmdb.sqlite").write_text(u"old")
    return root


def reimport_outputs(backend="bdb\n", imported="bash\nglibc\ngpg-pubkey\n", importdb=(0, b"", b"")):
    return {
        "rpmkeys": [(0, "", "")],
        "rpm": [(0, "", ""), (0, "", ""), (0, "bash\nglibc\n", "")],
        "chroot-rpm": [(0, backend.encode(), b""), (0, imported.encode(), b"")],
        "chroot-rpmdb": [(0, b"EXPORT", b""), importdb],
    }


def test_sqlite_database_is_reimported_when_the_installed_system_uses_bdb(run_module, tmp_path):
    root = make_root(tmp_path)
    result, calls = run_module(dict(root=str(root), packages=PACKAGES, reimport_rpmdb=True), reimport_outputs())
    assert result["changed"] is True
    assert result["rpmdb_reimported"] is True
    assert calls[-2][1][:4] == ["/usr/bin/chroot", str(root), "rpmdb", "--importdb"]
    assert calls[-2][2] == b"EXPORT"
    assert not (root / "var" / "lib" / "rpm" / "rpmdb.sqlite").exists()
    assert os.listdir(str(root / "var" / "tmp")) == []


def test_no_reimport_when_the_installed_system_uses_sqlite(run_module, tmp_path):
    root = make_root(tmp_path)
    outputs = reimport_outputs(backend="sqlite\n")
    outputs["chroot-rpmdb"] = []
    outputs["chroot-rpm"] = outputs["chroot-rpm"][:1]
    result, _calls = run_module(dict(root=str(root), packages=PACKAGES, reimport_rpmdb=True), outputs)
    assert result["rpmdb_reimported"] is False
    assert (root / "var" / "lib" / "rpm" / "rpmdb.sqlite").exists()


def test_no_reimport_when_there_is_no_sqlite_database(run_module, tmp_path):
    root = make_root(tmp_path)
    (root / "var" / "lib" / "rpm" / "rpmdb.sqlite").unlink()
    (root / "var" / "lib" / "rpm" / "Packages").write_text(u"bdb")
    outputs = reimport_outputs()
    outputs["chroot-rpm"] = []
    outputs["chroot-rpmdb"] = []
    result, _calls = run_module(dict(root=str(root), packages=PACKAGES, reimport_rpmdb=True), outputs)
    assert result["rpmdb_reimported"] is False
    assert result["changed"] is True


def test_reimport_is_done_when_nothing_was_installed_but_the_database_is_still_sqlite(run_module, tmp_path):
    root = make_root(tmp_path)
    outputs = reimport_outputs()
    outputs["rpm"] = [(0, "bash\nglibc\n", ""), (0, "bash\nglibc\n", "")]
    result, _calls = run_module(dict(root=str(root), packages=PACKAGES, reimport_rpmdb=True), outputs)
    assert result["rpmdb_reimported"] is True
    assert result["packages_installed"] == []


def test_failed_import_restores_the_old_database(run_module, tmp_path):
    root = make_root(tmp_path)
    outputs = reimport_outputs(importdb=(1, b"", b"bad"))
    result, _calls = run_module(dict(root=str(root), packages=PACKAGES, reimport_rpmdb=True), outputs)
    assert result["failed"] is True
    assert (root / "var" / "lib" / "rpm" / "rpmdb.sqlite").read_text() == u"old"


def test_a_reimported_database_with_other_packages_is_restored(run_module, tmp_path):
    root = make_root(tmp_path)
    outputs = reimport_outputs(imported="bash\n")
    result, _calls = run_module(dict(root=str(root), packages=PACKAGES, reimport_rpmdb=True), outputs)
    assert result["failed"] is True
    assert (root / "var" / "lib" / "rpm" / "rpmdb.sqlite").read_text() == u"old"


def test_check_mode_predicts_the_reimport_of_a_fresh_installation(run_module, tmp_path):
    root = make_root(tmp_path)
    result, calls = run_module(
        dict(root=str(root), packages=PACKAGES, reimport_rpmdb=True, _ansible_check_mode=True),
        {"rpmkeys": [(0, "", "")], "rpm": [(0, "", "")]})
    assert result["rpmdb_reimported"] is True
    assert (root / "var" / "lib" / "rpm" / "rpmdb.sqlite").exists()
    assert [call[0] for call in calls] == ["rpmkeys", "rpm"]
