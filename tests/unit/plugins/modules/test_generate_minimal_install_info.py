# SPDX-License-Identifier: EUPL-1.2
"""Unit tests for the generate_minimal_install_info module.

The python dnf module is replaced by a fake, so the tests need neither dnf nor network.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import contextlib
import json
import sys
import types
from unittest import mock

import pytest
from ansible.module_utils import basic
from ansible.module_utils.common.text.converters import to_bytes

try:
    from ansible.module_utils.testing import patch_module_args
except ImportError:  # ansible-core < 2.19

    @contextlib.contextmanager
    def patch_module_args(args):
        """Expose the module arguments to AnsibleModule on older ansible-core."""
        payload = to_bytes(json.dumps({"ANSIBLE_MODULE_ARGS": args}))
        with mock.patch.object(basic, "_ANSIBLE_ARGS", payload):
            yield


try:
    from ansible_collections.geertsky.tuxifier.plugins.modules import (
        generate_minimal_install_info as gmi,
    )
except ImportError:  # plain pytest run from the repository root
    import importlib
    import os

    sys.path.insert(
        0,
        os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "..", "plugins", "modules"
        ),
    )
    gmi = importlib.import_module("generate_minimal_install_info")


class FakePackage:
    """Stand-in for a dnf package in the transaction."""

    def __init__(self, name, url, epoch=0, version="1", release="1", arch="x86_64"):
        self.name = name
        self.epoch = epoch
        self.version = version
        self.release = release
        self.arch = arch
        self._url = url

    def remote_location(self):
        return self._url


class FakeGroup:
    def __init__(self, group_id):
        self.id = group_id


class FakeComps:
    def __init__(self, groups):
        self.groups = [FakeGroup(g) for g in groups]

    def group_by_pattern(self, pattern, case_sensitive=True):
        for group in self.groups:
            if group.id.lower() == pattern.lower():
                return group
        return None


class FakeRepo:
    baseurl = None
    metalink = None
    mirrorlist = None


class FakeBase:
    """Stand-in for dnf.Base. Class attributes are set by the fixture."""

    packages = []
    groups = ["core"]
    last = None

    def __init__(self):
        self.conf = types.SimpleNamespace(
            substitutions={}, optional_metadata_types=["primary"]
        )
        self.repos = types.SimpleNamespace(add_new_repo=self._add_new_repo)
        self.comps = FakeComps(self.groups)
        self.transaction = types.SimpleNamespace(install_set=list(self.packages))
        self.repo = FakeRepo()
        self.installed = []
        self.group_installed = []
        FakeBase.last = self

    def _add_new_repo(self, repo_id, conf):
        self.repo_id = repo_id
        return self.repo

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def fill_sack(self, **kwargs):
        self.sack_kwargs = kwargs

    def read_comps(self, **kwargs):
        pass

    def install(self, spec, **kwargs):
        self.installed.append(spec)

    def group_install(self, group_id, types_, **kwargs):
        self.group_installed.append((group_id, types_))

    def resolve(self):
        pass


@pytest.fixture(name="fake_dnf")
def fixture_fake_dnf(monkeypatch):
    FakeBase.packages = [
        FakePackage("bash", "http://m/bash.rpm"),
        FakePackage("kernel", "http://m/kernel.rpm"),
    ]
    FakeBase.groups = ["core"]
    module = types.ModuleType("dnf")
    module.Base = FakeBase
    monkeypatch.setitem(sys.modules, "dnf", module)
    return FakeBase


def make_distribution(**overrides):
    distribution = {
        "name": "rocky",
        "version": "10",
        "arch": "x86_64",
        "repo": {"type": "baseurl", "url": "http://m/os/"},
        "minimalpackages": ["@Core", "kernel"],
    }
    distribution.update(overrides)
    return distribution


def test_missing_dnf_raises_runtime_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "dnf", None)  # makes "import dnf" fail
    with pytest.raises(RuntimeError, match="dnf module is required"):
        gmi.generate_packages(make_distribution())


@pytest.mark.parametrize("specs", [[], [""], ["   ", None]])
def test_empty_package_list_is_rejected(fake_dnf, specs):
    with pytest.raises(ValueError, match="at least one package"):
        gmi.generate_packages(make_distribution(minimalpackages=specs))


def test_resolves_packages_and_groups(fake_dnf):
    result = gmi.generate_packages(make_distribution())
    assert result == [
        {"name": "bash", "url": "http://m/bash.rpm"},
        {"name": "kernel", "url": "http://m/kernel.rpm"},
    ]
    base = fake_dnf.last
    assert base.group_installed == [("core", gmi.GROUP_PACKAGE_TYPES)]
    assert base.installed == ["kernel"]
    assert base.conf.substitutions["releasever"] == "10"
    assert base.conf.substitutions["basearch"] == "x86_64"
    assert "filelists" in base.conf.optional_metadata_types
    assert base.repo_id == "rocky-10"
    assert base.sack_kwargs == {"load_system_repo": False, "load_available_repos": True}


@pytest.mark.parametrize("repo_type", ["baseurl", "metalink", "mirrorlist"])
def test_repo_types(fake_dnf, repo_type):
    gmi.generate_packages(
        make_distribution(repo={"type": repo_type.upper(), "url": " http://m/r "})
    )
    repo = fake_dnf.last.repo
    value = getattr(repo, repo_type)
    assert value in ("http://m/r", ["http://m/r"])


def test_unsupported_repo_type(fake_dnf):
    with pytest.raises(ValueError, match="Unsupported repository type"):
        gmi.generate_packages(make_distribution(repo={"type": "ftp", "url": "x"}))


def test_unknown_group_lists_available_groups(fake_dnf):
    with pytest.raises(ValueError, match="'@nope' was not found.*core"):
        gmi.generate_packages(make_distribution(minimalpackages=["@nope"]))


def test_empty_group_spec(fake_dnf):
    with pytest.raises(ValueError, match="empty DNF group"):
        gmi.generate_packages(make_distribution(minimalpackages=["@ "]))


def test_missing_remote_location(fake_dnf):
    fake_dnf.packages = [FakePackage("bash", None)]
    with pytest.raises(RuntimeError, match="remote URL"):
        gmi.generate_packages(make_distribution())


def test_duplicate_urls_are_removed(fake_dnf):
    fake_dnf.packages = [
        FakePackage("bash", "http://m/bash.rpm", release="1"),
        FakePackage("bash", "http://m/bash.rpm", release="2"),
    ]
    assert gmi.generate_packages(make_distribution()) == [
        {"name": "bash", "url": "http://m/bash.rpm"}
    ]


def test_packages_are_sorted(fake_dnf):
    fake_dnf.packages = [
        FakePackage("zsh", "http://m/zsh.rpm"),
        FakePackage("bash", "http://m/bash.rpm"),
    ]
    names = [p["name"] for p in gmi.generate_packages(make_distribution())]
    assert names == ["bash", "zsh"]


class ExitJson(Exception):
    def __init__(self, kwargs):
        super().__init__()
        self.kwargs = kwargs


def run_with_args(monkeypatch, args):
    """Run run_module() with module arguments; return the exit_json/fail_json kwargs."""

    def exit_json(self, **kwargs):
        raise ExitJson(dict(kwargs, failed=False))

    def fail_json(self, **kwargs):
        raise ExitJson(dict(kwargs, failed=True))

    monkeypatch.setattr(basic.AnsibleModule, "exit_json", exit_json)
    monkeypatch.setattr(basic.AnsibleModule, "fail_json", fail_json)
    with patch_module_args(args), pytest.raises(ExitJson) as excinfo:
        gmi.run_module()
    return excinfo.value.kwargs


def test_run_module_success(fake_dnf, monkeypatch):
    result = run_with_args(monkeypatch, {"distribution": make_distribution()})
    assert result["failed"] is False
    assert result["changed"] is False
    assert result["package_count"] == 2
    assert result["rpm_urls"] == "http://m/bash.rpm http://m/kernel.rpm"


def test_run_module_reports_errors(fake_dnf, monkeypatch):
    result = run_with_args(
        monkeypatch, {"distribution": make_distribution(minimalpackages=["@nope"])}
    )
    assert result["failed"] is True
    assert "not found" in result["msg"]


def test_run_module_rejects_bad_repo_type(fake_dnf, monkeypatch):
    result = run_with_args(
        monkeypatch,
        {"distribution": make_distribution(repo={"type": "ftp", "url": "x"})},
    )
    assert result["failed"] is True
    assert "ftp" in result["msg"]


def test_main_calls_run_module():
    with mock.patch.object(gmi, "run_module") as run_module:
        gmi.main()
    run_module.assert_called_once_with()
