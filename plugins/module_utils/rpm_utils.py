# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Geert Geurts <geert@verweggistan.eu>
# European Union Public Licence v. 1.2 (see LICENSE or
# https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12)

"""Helpers for the geertsky.tuxifier.rpm_install module.

RpmRunner builds every rpm command line as an argv list, with one --root and one set of
--define options for all commands.
"""

from __future__ import absolute_import, division, print_function

import base64
import hashlib
import re

__metaclass__ = type

# Output of ``rpmkeys --list`` starts with the 40 digit fingerprint of the key.
LEADING_FINGERPRINT_RE = re.compile(r"^[0-9A-Fa-f]{40}")
ARMOR_RE = re.compile(
    r"-----BEGIN PGP PUBLIC KEY BLOCK-----(.*?)-----END PGP PUBLIC KEY BLOCK-----",
    re.DOTALL,
)

TAG_PUBLIC_KEY = 6

# Parsing output needs a stable locale.
C_LOCALE = dict(LANG="C", LC_ALL="C")

# The rpm of the installed system lists an imported key as a package with this name.


def parse_key_list(output):
    """Return the upper-case fingerprints at the start of the lines of ``rpmkeys --list``."""
    fingerprints = []
    for line in output.splitlines():
        match = LEADING_FINGERPRINT_RE.match(line)
        if match:
            fingerprints.append(match.group(0).upper())
    return fingerprints


def dearmor(text):
    """Return the binary OpenPGP data of every armored block in ``text``."""
    blocks = []
    for body in ARMOR_RE.findall(text):
        lines = body.strip().splitlines()
        # Armor headers (Version: ...) end at the first blank line.
        if any(not line.strip() for line in lines):
            lines = lines[[bool(line.strip()) for line in lines].index(False) + 1:]
        data = "".join(line.strip() for line in lines if line.strip() and not line.startswith("="))
        blocks.append(base64.b64decode(data))
    return blocks


def iter_packets(data):
    """Yield ``(tag, body)`` for every OpenPGP packet in ``data`` (RFC 4880 section 4)."""
    position = 0
    while position < len(data):
        header = data[position]
        position += 1
        if not header & 0x80:
            raise ValueError("invalid OpenPGP packet header")
        if header & 0x40:
            tag = header & 0x3F
            first = data[position]
            position += 1
            if first < 192:
                length = first
            elif first < 224:
                length = ((first - 192) << 8) + data[position] + 192
                position += 1
            elif first == 255:
                length = int.from_bytes(data[position:position + 4], "big")
                position += 4
            else:
                raise ValueError("partial length OpenPGP packets are not supported")
        else:
            tag = (header >> 2) & 0x0F
            length_type = header & 0x03
            if length_type == 3:
                length = len(data) - position
            else:
                size = (1, 2, 4)[length_type]
                length = int.from_bytes(data[position:position + size], "big")
                position += size
        body = data[position:position + length]
        if len(body) != length:
            raise ValueError("truncated OpenPGP packet")
        position += length
        yield tag, body


def key_fingerprints(text):
    """Return the upper-case v4 fingerprints of all primary keys in armored ``text``.

    Raises ValueError when the text holds no key, or a key that is not a version 4 key.
    """
    fingerprints = []
    for data in dearmor(text):
        for tag, body in iter_packets(data):
            if tag != TAG_PUBLIC_KEY:
                continue
            if body[0] != 4:
                raise ValueError("only OpenPGP version 4 keys are supported, found version %d" % body[0])
            digest = hashlib.sha1(b"\x99" + len(body).to_bytes(2, "big") + body)
            fingerprints.append(digest.hexdigest().upper())
    if not fingerprints:
        raise ValueError("no OpenPGP public key found")
    return fingerprints


def missing_packages(requested, installed_names):
    """Return the requested packages whose name is not installed, in request order."""
    installed = set(installed_names)
    seen = set()
    missing = []
    for package in requested:
        if package["name"] not in installed and package["url"] not in seen:
            seen.add(package["url"])
            missing.append(package)
    return missing


class RpmRunner(object):
    """Build and run rpm family commands for one root and one set of macros."""

    def __init__(self, module, root=None, macros=None):
        self.module = module
        self.root = root
        self.macros = macros or {}

    def argv(self, program, *args):
        """Return ``[program, --root R, --define 'k v', *args]`` with the program resolved."""
        command = [self.module.get_bin_path(program, required=True)]
        if self.root:
            command += ["--root", self.root]
        for name in sorted(self.macros):
            command += ["--define", "%s %s" % (name, self.macros[name])]
        return command + list(args)

    def run(self, program, *args, **kwargs):
        """Run an rpm command and fail the module, with all context, when it exits non-zero."""
        data = kwargs.pop("data", None)
        check_rc = kwargs.pop("check_rc", True)
        if kwargs:
            raise TypeError("unexpected keyword arguments: %s" % ", ".join(sorted(kwargs)))
        return self.execute(self.argv(program, *args), data=data, check_rc=check_rc)

    def execute(self, command, data=None, check_rc=True, raw=False):
        """Run ``command`` (an argv list). With ``raw`` stdin and the returned stdout are bytes."""
        rc, stdout, stderr = self.module.run_command(
            command,
            data=data,
            binary_data=raw,
            encoding=None if raw else "utf-8",
            environ_update=C_LOCALE,
        )
        if check_rc and rc != 0:
            self.module.fail_json(
                msg="%s failed with exit code %d" % (command[0], rc),
                cmd=command,
                rc=rc,
                stdout=stdout,
                stderr=stderr,
            )
        return rc, stdout, stderr

    def installed_names(self):
        """Return the NAME of every installed package, one entry per package."""
        _rc, stdout, _err = self.run("rpm", "-qa", "--queryformat", "%{NAME}\\n")
        return [line for line in stdout.splitlines() if line]

    def imported_fingerprints(self):
        """Return the upper-case fingerprints of all imported GPG keys."""
        _rc, stdout, _err = self.run("rpmkeys", "--list")
        return parse_key_list(stdout)
