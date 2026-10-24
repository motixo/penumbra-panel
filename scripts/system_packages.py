"""Query native COSMIC packages and retain exact upgrade guards on each distro."""

import platform
import re
import subprocess


def backend():
    try:
        release = platform.freedesktop_os_release()
    except OSError as error:
        raise RuntimeError("Cannot identify this Linux distribution.") from error
    distro = release.get("ID", "")
    if distro == "fedora":
        return "rpm"
    if distro == "arch" or "arch" in release.get("ID_LIKE", "").split():
        return "pacman"
    raise RuntimeError("Penumbra supports Arch Linux and Fedora with COSMIC 1.10.0 or 1.11.0.")


def query_command(name, manager):
    if manager == "pacman":
        return ["pacman", "-Q", name]
    if manager == "rpm":
        return ["rpm", "-q", "--qf", "%{NAME} %{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}\\n", name]
    raise ValueError("Unsupported package manager: " + manager)


def query(name, manager):
    try:
        result = subprocess.check_output(query_command(name, manager), text=True, stderr=subprocess.PIPE).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError(f"Cannot query {name} with {manager}. Install the native COSMIC packages first.") from error
    # Reject prereleases and multiple installed architectures instead of guessing.
    upstream_version(name, result)
    return result


def upstream_version(name, package):
    match = re.fullmatch(re.escape(name) + r" (?:[0-9]+:)?([0-9]+\.[0-9]+\.[0-9]+)-[^\s]+", package)
    if not match:
        raise RuntimeError("Unsupported package: " + package)
    return match[1]
