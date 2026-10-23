"""Normalize only a recognized Ubuntu 24.04 CI APT source; never run APT.

This is for disposable GitHub-hosted CI machines, not ATLAS source hosts.
Package authentication and the complete Playwright dependency command stay
unchanged. Unknown source layouts fail before replacing any bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile


_KEYRING = "/usr/share/keyrings/ubuntu-archive-keyring.gpg"
_URIS = frozenset({
    "http://azure.archive.ubuntu.com/ubuntu", "https://azure.archive.ubuntu.com/ubuntu",
    "http://archive.ubuntu.com/ubuntu", "https://archive.ubuntu.com/ubuntu",
    "http://security.ubuntu.com/ubuntu", "https://security.ubuntu.com/ubuntu",
    "mirror+file:/etc/apt/apt-mirrors.txt", "mirror+file:/etc/apt/apt-security-mirrors.txt",
})
_SUITES = frozenset({"noble", "noble-updates", "noble-backports", "noble-security"})
_COMPONENTS = frozenset({"main", "restricted", "universe", "multiverse"})
_FIELDS = frozenset({"Types", "URIs", "Suites", "Components", "Signed-By", "Architectures"})


def normalize_sources(source: str) -> str:
    """Preserve every suite/component/signing field and use official HTTPS.

    A combined stanza is split only to send its security suite to the official
    security archive. No source is added, enabled or silently discarded.
    """
    if not isinstance(source, str) or not source.strip() or "\x00" in source:
        raise ValueError("CI_UBUNTU_SOURCE_INVALID")
    output = []
    stanza_count = 0
    for paragraph in re.split(r"\n[ \t]*\n", source.strip("\n")):
        comments, entries, fields = [], [], {}
        for line in paragraph.splitlines():
            if line.startswith("#"):
                comments.append(line)
                continue
            # The supported runner source has simple, single-line fields.
            # Reject continuations/duplicates instead of guessing their meaning.
            match = re.fullmatch(r"([A-Za-z][A-Za-z-]*):[ \t]*(\S.*)", line)
            if not match:
                raise ValueError("CI_UBUNTU_SOURCE_LAYOUT_UNRECOGNIZED")
            key, value = match.groups()
            if key not in _FIELDS or key in fields:
                raise ValueError("CI_UBUNTU_SOURCE_FIELD_UNRECOGNIZED")
            fields[key] = value.rstrip()
            entries.append(key)
        if not fields and comments:
            output.append("\n".join(comments))
            continue
        if not fields or set(fields) - {"Architectures"} != _FIELDS - {"Architectures"}:
            raise ValueError("CI_UBUNTU_SOURCE_FIELDS_INCOMPLETE")
        stanza_count += 1
        if not set(fields["Types"].split()) <= {"deb", "deb-src"}:
            raise ValueError("CI_UBUNTU_SOURCE_TYPES_UNRECOGNIZED")
        if fields["Signed-By"] != _KEYRING:
            raise ValueError("CI_UBUNTU_SOURCE_SIGNING_KEY_UNRECOGNIZED")
        if "Architectures" in fields and fields["Architectures"] != "amd64":
            raise ValueError("CI_UBUNTU_SOURCE_ARCHITECTURE_UNRECOGNIZED")
        uris = fields["URIs"].split()
        if any(uri.rstrip("/") not in _URIS for uri in uris):
            raise ValueError("CI_UBUNTU_SOURCE_MIRROR_UNRECOGNIZED")
        suites, components = fields["Suites"].split(), fields["Components"].split()
        if len(suites) != len(set(suites)) or not set(suites) <= _SUITES:
            raise ValueError("CI_UBUNTU_SOURCE_SUITE_UNRECOGNIZED")
        if len(components) != len(set(components)) or not set(components) <= _COMPONENTS:
            raise ValueError("CI_UBUNTU_SOURCE_COMPONENT_UNRECOGNIZED")
        for security in (False, True):
            selected = [suite for suite in suites if (suite == "noble-security") == security]
            if not selected:
                continue
            updated = dict(fields)
            updated["Suites"] = " ".join(selected)
            updated["URIs"] = ("https://security.ubuntu.com/ubuntu" if security else
                               "https://archive.ubuntu.com/ubuntu")
            output.append("\n".join(comments + [f"{key}: {updated[key]}" for key in entries]))
    if not stanza_count:
        raise ValueError("CI_UBUNTU_SOURCE_FIELDS_INCOMPLETE")
    return "\n\n".join(output) + "\n"


def normalize_file(path: Path, *, os_release: str) -> dict[str, str | bool]:
    identity = dict(line.split("=", 1) for line in os_release.splitlines()
                    if "=" in line and not line.startswith("#"))
    if identity.get("ID", "").strip('"') != "ubuntu" or identity.get("VERSION_ID", "").strip('"') != "24.04":
        raise ValueError("CI_UBUNTU_RELEASE_UNRECOGNIZED")
    original_stat = path.lstat()
    if not stat.S_ISREG(original_stat.st_mode) or original_stat.st_nlink != 1:
        raise ValueError("CI_UBUNTU_SOURCE_MUST_BE_REGULAR_UNALIASED_FILE")
    original = path.read_bytes()
    updated = normalize_sources(original.decode("utf-8")).encode("utf-8")
    receipt = {"changed": updated != original,
               "before_sha256": hashlib.sha256(original).hexdigest(),
               "after_sha256": hashlib.sha256(updated).hexdigest()}
    if updated == original:
        return receipt
    temporary = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=".atlas-ci-ubuntu-", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as handle:
            os.fchmod(handle.fileno(), stat.S_IMODE(original_stat.st_mode))
            os.fchown(handle.fileno(), original_stat.st_uid, original_stat.st_gid)
            handle.write(updated)
            handle.flush()
            os.fsync(handle.fileno())
        current = path.lstat()
        if ((current.st_dev, current.st_ino, current.st_mode, current.st_nlink)
                != (original_stat.st_dev, original_stat.st_ino, original_stat.st_mode, original_stat.st_nlink)
                or path.read_bytes() != original):
            raise ValueError("CI_UBUNTU_SOURCE_CHANGED_DURING_REVIEW")
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-file", type=Path,
                        default=Path("/etc/apt/sources.list.d/ubuntu.sources"))
    args = parser.parse_args()
    try:
        receipt = normalize_file(args.source_file, os_release=Path("/etc/os-release").read_text())
    except (OSError, ValueError, UnicodeError):
        print("CI_UBUNTU_MIRROR_NORMALIZATION_FAILED")
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
