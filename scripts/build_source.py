#!/usr/bin/env python3
"""Build both patched COSMIC programs from their pinned upstream sources."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

import install_prebuilt
import panel_control as manager

ROOT = Path(__file__).resolve().parents[1]


def prepare(root, destination, release):
    sources = {}
    for key, component in release["upstreams"].items():
        source = destination / key
        subprocess.run(["git", "clone", "--depth", "1", "--single-branch", "--branch", component["ref"],
                        "https://github.com/" + component["repository"] + ".git", str(source)], check=True)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
        if commit != component["commit"]:
            raise RuntimeError(f"Upstream {key} tag no longer identifies the tested commit.")
        patch = root / component["patch"]
        subprocess.run(["git", "apply", "--check", str(patch)], cwd=source, check=True)
        subprocess.run(["git", "apply", str(patch)], cwd=source, check=True)
        sources[key] = source
    return sources


def build(root, work, release, jobs):
    sources = prepare(root, work, release)
    target = Path(os.environ.get("CARGO_TARGET_DIR", work / "target"))
    if not target.is_absolute():
        raise ValueError("CARGO_TARGET_DIR must be an absolute path")
    env = dict(os.environ, CARGO_TARGET_DIR=str(target), CARGO_BUILD_JOBS=str(jobs))
    output = work / "binaries"
    output.mkdir()
    binaries = {}
    for key, source in sources.items():
        component = release["upstreams"][key]
        command = ["cargo", "test", "--release", "--locked", "-p", component["cargo_package"]]
        if key == "settings":
            command.append("pages::desktop::panel::gradient::tests")
        subprocess.run(command, cwd=source, env=env, check=True)
        subprocess.run(["cargo", "build", "--release", "--locked", "-p", component["cargo_package"]], cwd=source, env=env, check=True)
        destination = output / component["binary"]
        shutil.copy2(target / "release" / component["binary"], destination)
        subprocess.run(["strip", "--strip-unneeded", str(destination)], check=True)
        binaries[component["binary"]] = destination
    bundle = make_bundle(binaries, release)
    (output / "bundle.json").write_text(json.dumps(bundle, indent=2) + "\n")
    return sources, binaries, bundle


def make_bundle(binaries, release):
    details = {}
    for name, path in binaries.items():
        version = subprocess.run([str(path), "--version"], check=True, text=True, capture_output=True).stdout.strip()
        details[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "version": version}
    return {**release, "architecture": platform.machine().lower(), "binaries": details}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="Panel", help="Panel profile to enable after building")
    parser.add_argument("--no-activate", action="store_true", help="Keep gradient preferences unchanged")
    parser.add_argument("--build-only", action="store_true", help="Build and test without installing")
    parser.add_argument("--jobs", type=int, default=int(os.environ.get("CARGO_BUILD_JOBS", "4")))
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error("Run as your normal desktop user, without sudo.")
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    try:
        release = json.loads((ROOT / "release.json").read_text())
        install_prebuilt.check_platform(release, binary=False)
        if not args.build_only:
            manager.require_profile(args.profile)
            for name in manager.PROGRAMS:
                manager.owned_launcher(manager.BIN / name, allow_legacy=True)
        cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "penumbra-panel"
        cache.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="build-", dir=cache))
        print(f"Source and build files: {work}", flush=True)
        _, binaries, bundle = build(ROOT, work, release, args.jobs)
        install_prebuilt.check_bundle(binaries, bundle, release, source=True)
        if args.build_only:
            print(f"Build complete. Binaries: {work / 'binaries'}")
        else:
            manager.install(binaries, bundle, release, args.profile, not args.no_activate)
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Build failed: {error}\n")


if __name__ == "__main__":
    main()
