#!/usr/bin/env python3
"""Install a verified Penumbra Panel binary release, without Cargo or Rust."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

import panel_control as manager

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "penumbra-panel"
ASSET = "penumbra-panel-linux-x86_64.tar.gz"
LIMIT = 256 * 1024 * 1024


def download(url, destination, limit=LIMIT):
    request = urllib.request.Request(url, headers={"User-Agent": "penumbra-panel-installer"})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
        total = 0
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > limit:
                raise RuntimeError("The release download exceeds the expected size.")
            output.write(block)


def verify_checksum(path, checksums):
    matches = [line.split()[0] for line in checksums.splitlines()
               if len(line.split()) == 2 and line.split()[1].lstrip("*") == path.name]
    if len(matches) != 1 or not re.fullmatch(r"[0-9a-fA-F]{64}", matches[0]):
        raise RuntimeError("The checksum file does not identify this release archive.")
    if hashlib.sha256(path.read_bytes()).hexdigest() != matches[0].lower():
        raise RuntimeError("Release checksum mismatch; nothing was installed.")


def read_member(archive, name, limit):
    matches = [member for member in archive.getmembers() if member.name == name]
    if len(matches) != 1 or not matches[0].isfile() or not 0 <= matches[0].size <= limit:
        raise RuntimeError(f"Invalid release archive member: {name}")
    with archive.extractfile(matches[0]) as stream:
        return stream.read()


def unpack(archive_path, destination):
    # Only read named regular files; paths and links in a tarball are never extracted.
    with tarfile.open(archive_path, "r:gz") as archive:
        bundle = json.loads(read_member(archive, f"{PREFIX}/bundle.json", 32768))
        binaries = {}
        for name in manager.PROGRAMS:
            path = destination / name
            path.write_bytes(read_member(archive, f"{PREFIX}/bin/{name}", LIMIT))
            path.chmod(0o755)
            binaries[name] = path
    return binaries, bundle


def check_platform(release, binary=True):
    if platform.system() != "Linux":
        raise RuntimeError("Penumbra Panel requires Linux and COSMIC.")
    manager.package_versions(release)
    if not binary:
        return
    if platform.machine().lower() not in ("x86_64", "amd64"):
        raise RuntimeError("The binary release requires x86_64. Use ./install.sh --from-source instead.")
    try:
        libc = os.confstr("CS_GNU_LIBC_VERSION") or ""
    except (OSError, ValueError):
        libc = ""
    if not libc.startswith("glibc "):
        raise RuntimeError("The binary release requires glibc. Use a source build instead.")
    parse = lambda value: tuple(int(part) for part in value.split("."))
    if parse(libc.split()[1]) < parse(release["minimum_glibc"]):
        raise RuntimeError(f"This binary needs glibc {release['minimum_glibc']} or newer. Build from source on this system instead.")


def check_bundle(binaries, bundle, release, source=False):
    for key in ("version", "repository", "upstreams"):
        if bundle.get(key) != release[key]:
            raise RuntimeError(f"The release bundle has an unexpected {key}.")
    if not source and bundle.get("architecture") != release["architecture"]:
        raise RuntimeError("The release bundle has an unexpected architecture.")
    for name in manager.PROGRAMS:
        details = bundle["binaries"][name]
        content = binaries[name].read_bytes()
        if hashlib.sha256(content).hexdigest() != details["sha256"]:
            raise RuntimeError(f"Checksum mismatch for {name}; nothing was installed.")
        if content[:4] != b"\x7fELF":
            raise RuntimeError(f"{name} is not a Linux ELF executable.")
        expected = f"{name} 1.9.0 + penumbra-panel {release['version']}"
        if details["version"] != expected:
            raise RuntimeError(f"Unexpected binary version for {name}.")
        result = subprocess.run([str(binaries[name]), "--version"], capture_output=True, text=True, timeout=15)
        if result.returncode or result.stdout.strip() != expected:
            detail = result.stderr.strip() or result.stdout.strip() or f"exit status {result.returncode}"
            raise RuntimeError(f"{name} cannot run on this system: {detail}")


def fetch(release, destination):
    base = f"https://github.com/{release['repository']}/releases/download/v{release['version']}"
    archive = destination / ASSET
    checksums = destination / "SHA256SUMS"
    print(f"Downloading Penumbra Panel {release['version']}…", flush=True)
    download(base + "/SHA256SUMS", checksums, 1024 * 1024)
    download(base + "/" + ASSET, archive)
    verify_checksum(archive, checksums.read_text())
    return unpack(archive, destination)


def install_release(root, profile="Panel", activate=True):
    release = json.loads((root / "release.json").read_text())
    check_platform(release)
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", release["version"]):
        raise ValueError("Invalid release version")
    manager.require_profile(profile)
    for name in manager.PROGRAMS:
        manager.owned_launcher(manager.BIN / name, allow_legacy=True)
    with tempfile.TemporaryDirectory(prefix="penumbra-panel-install-") as temporary:
        if (root / "bundle.json").is_file():
            binaries = {name: root / "bin" / name for name in manager.PROGRAMS}
            bundle = json.loads((root / "bundle.json").read_text())
        else:
            binaries, bundle = fetch(release, Path(temporary))
        check_bundle(binaries, bundle, release)
        manager.install(binaries, bundle, release, profile, activate)


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog="Build instead: ./install.sh --from-source [--build-only]")
    parser.add_argument("--profile", default="Panel", help="Existing panel profile to enable (default: Panel)")
    parser.add_argument("--no-activate", action="store_true", help="Keep all saved gradient preferences unchanged")
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error("Run as your normal desktop user, without sudo.")
    try:
        install_release(ROOT, args.profile, not args.no_activate)
    except (OSError, RuntimeError, ValueError, KeyError, tarfile.TarError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Install failed: {error}\n")


if __name__ == "__main__":
    main()
