#!/usr/bin/env python3
"""Manage the per-user Penumbra Panel installation without stopping processes."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile

NAME = "penumbra-panel"
MARKER = "# Managed by penumbra-panel"
LEGACY_MARKER = "# Managed by cosmic-top-panel-gradient"
DATA = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / NAME
STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / NAME
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "cosmic"
BIN = Path.home() / ".local/bin"
PROGRAMS = ("cosmic-panel", "cosmic-settings")


def atomic(path, content, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            os.fchmod(stream.fileno(), mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def preference_file(profile):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", profile):
        raise ValueError("Invalid panel profile name")
    return CONFIG / ("com.system76.CosmicPanel." + profile) / "v1/top_edge_gradient"


def require_profile(profile):
    base = preference_file(profile).parent
    anchor = base / "anchor"
    if not anchor.is_file() or anchor.read_text().strip() not in {"Top", "Bottom", "Left", "Right"}:
        raise ValueError(f"Panel profile {profile!r} does not exist. Create it in COSMIC Settings first.")


def package_versions(release):
    versions = {}
    for component in release["upstreams"].values():
        name = component["binary"]
        try:
            actual = subprocess.check_output(["pacman", "-Q", name], text=True, stderr=subprocess.PIPE).strip()
        except (OSError, subprocess.CalledProcessError) as error:
            raise RuntimeError("This release requires Arch Linux with the supported COSMIC packages.") from error
        if actual != component["package"]:
            raise RuntimeError(f"Unsupported package: {actual}. This patch requires {component['package']}.")
        versions[name] = actual
    return versions


def owned_launcher(path, allow_legacy=False):
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"A different override already exists: {path}")
    contents = path.read_bytes()
    markers = [MARKER] + ([LEGACY_MARKER] if allow_legacy else [])
    if not any(marker.encode() in contents.splitlines() for marker in markers):
        raise ValueError(f"A different override already exists: {path}")
    return contents


def launcher(binary, packages):
    lines = ["#!/bin/sh", MARKER]
    for index, (name, version) in enumerate(sorted(packages.items())):
        lines.append(f"package_{index}=$(pacman -Q {shlex.quote(name)} 2>/dev/null) || package_{index}=")
    checks = [f'[ "$package_{index}" = {shlex.quote(version)} ]' for index, (_, version) in enumerate(sorted(packages.items()))]
    destination = DATA / "versions" / binary.parent.name / binary.name
    checks.append(f"[ -x {shlex.quote(str(destination))} ]")
    lines += ["if " + " && ".join(checks) + "; then",
              f'    exec {shlex.quote(str(destination))} "$@"', "fi",
              f'exec /usr/bin/{binary.name} "$@"', ""]
    return "\n".join(lines).encode()


def restore(path, previous, mode=0o600):
    if previous is None:
        path.unlink(missing_ok=True)
    else:
        atomic(path, previous, mode)


def install(binaries, bundle, release, profile="Panel", activate=True):
    require_profile(profile)
    packages = package_versions(release)
    previous_launchers = {name: owned_launcher(BIN / name, allow_legacy=True) for name in PROGRAMS}
    state_file = STATE / "install.json"
    previous_state = state_file.read_bytes() if state_file.exists() else None
    saved = json.loads(previous_state) if previous_state else {}
    preference = preference_file(profile)
    previous_preference = preference.read_bytes() if preference.exists() else None
    digest = hashlib.sha256(b"".join(binaries[name].read_bytes() for name in PROGRAMS)).hexdigest()[:16]
    version_dir = DATA / "versions" / (release["version"] + "-" + digest)
    # Prepare both binaries completely before redirecting either launcher.
    for name in PROGRAMS:
        atomic(version_dir / name, binaries[name].read_bytes(), 0o755)
    atomic(version_dir / "bundle.json", (json.dumps(bundle, indent=2) + "\n").encode())
    profiles = sorted(set(saved.get("profiles", [])) | {profile})
    original = saved.get("original_preferences", {})
    if profile not in original:
        original[profile] = previous_preference.decode() if previous_preference is not None else None
    state = {"version": release["version"], "directory": str(version_dir), "profiles": profiles,
             "original_preferences": original, "packages": packages}
    changed_preference = activate and previous_preference is None
    try:
        atomic(state_file, (json.dumps(state, indent=2) + "\n").encode())
        if changed_preference:
            atomic(preference, b"Some((enabled: true, height: 96, maximized_opacity: 0.96))\n")
        for name in PROGRAMS:
            atomic(BIN / name, launcher(version_dir / name, packages), 0o755)
    except BaseException:
        for name, previous in previous_launchers.items():
            restore(BIN / name, previous, 0o755)
        if changed_preference:
            restore(preference, previous_preference)
        restore(state_file, previous_state)
        raise
    print(f"Installed Penumbra Panel {release['version']} for {profile}.")
    print("Log out and back in, then open Settings → Desktop → Panel → Style → Panel gradient.")
    print("For the dock, use the same switch on the Dock page. Turn Gap off to use the gradient.")
    if shutil.which("cosmic-panel") != str(BIN / "cosmic-panel"):
        print(f"Your session PATH must put {BIN} before /usr/bin before you log in again.")


def uninstall(purge=False):
    state_file = STATE / "install.json"
    if not state_file.is_file():
        raise ValueError("Penumbra Panel is not installed for this user.")
    # Check both before touching either: another override may have replaced one.
    for name in PROGRAMS:
        owned_launcher(BIN / name)
    for name in PROGRAMS:
        (BIN / name).unlink(missing_ok=True)
    if DATA.exists():
        shutil.rmtree(DATA)
    if purge:
        for path in CONFIG.glob("com.system76.CosmicPanel.*/v1/top_edge_gradient"):
            path.unlink()
        shutil.rmtree(STATE)
    else:
        atomic(STATE / "last-install.json", state_file.read_bytes())
        state_file.unlink()
    print("Removed Penumbra Panel. Log out and back in to load the stock panel, and reopen Settings.")
    if not purge:
        print("Gradient preferences are kept for a later reinstall.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    remove = sub.add_parser("uninstall", help="Restore the stock panel and Settings")
    remove.add_argument("--purge", action="store_true", help="Also remove gradient preferences and installer state")
    sub.add_parser("status", help="Show installation metadata")
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error("Run as your normal desktop user, without sudo.")
    try:
        if args.command == "uninstall":
            uninstall(args.purge)
        else:
            path = STATE / "install.json"
            print(path.read_text().strip() if path.exists() else "Penumbra Panel is not installed.")
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
