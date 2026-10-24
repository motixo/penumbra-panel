#!/usr/bin/env python3
"""Package the binary installer and complete patched source for a release."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile

import build_source
import install_prebuilt
import release_config

ROOT = Path(__file__).resolve().parents[1]
FILES = ["README.md", "LICENSE", "NOTICE", "RELEASE_NOTES.md", "release.json",
         "install.sh", "uninstall.sh", "build-from-source.sh", "panel-gradient.patch",
         "settings-gradient-toggle.patch", "assets/screenshot-light.png", "assets/screenshot-dark.png",
         "scripts/panel_control.py", "scripts/install_prebuilt.py", "scripts/build_source.py",
         "scripts/build_release.py", "scripts/package_release.py", "scripts/release_config.py",
         "scripts/system_packages.py", "scripts/verify_release.py"]


def add_bytes(archive, name, content, mode=0o644):
    info = tarfile.TarInfo(name)
    info.size = len(content)
    info.mode = mode
    info.mtime = 0
    archive.addfile(info, io.BytesIO(content))


def add_file(archive, path, name):
    archive.add(path, arcname=name, recursive=False)


def source_files(source):
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=source).split(b"\0")
    # Added modules are not committed in the temporary upstream workspaces.
    added = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=source).split(b"\0")
    for entry in sorted(set(tracked + added)):
        if not entry:
            continue
        relative = Path(entry.decode())
        if relative == Path(".cargo/config.toml"):
            # Added below with the release's relative vendor path.
            continue
        if any(part in {".git", "target", "work", "__pycache__"} for part in relative.parts):
            continue
        path = source / relative
        if path.is_file() or path.is_symlink():
            yield path, relative.as_posix()


def package(binaries, sources, vendors, vendor_configs, output, release=None):
    release = release or release_config.select(json.loads((ROOT / "release.json").read_text()), "1.10.0")
    bundle = build_source.make_bundle(binaries, release)
    install_prebuilt.check_bundle(binaries, bundle, release)
    baseline = tuple(map(int, release["minimum_glibc"].split(".")))
    for path in binaries.values():
        symbols = subprocess.check_output(["readelf", "--version-info", str(path)], text=True)
        required = [tuple(map(int, version.split("."))) for version in re.findall(r"GLIBC_([0-9.]+)", symbols)]
        if required and max(required) > baseline:
            raise RuntimeError("This build needs a newer glibc than release.json declares. Update the release baseline before publishing.")
    if any(not vendors[key].is_dir() or not vendor_configs[key].is_file() for key in sources):
        raise ValueError("Vendored dependencies and their Cargo configuration are required.")
    output.mkdir(parents=True, exist_ok=True)
    binary_archive = output / release_config.asset(release)
    with tarfile.open(binary_archive, "w:gz") as archive:
        for name in FILES:
            content = (json.dumps(release, indent=2) + "\n").encode() if name == "release.json" else (ROOT / name).read_bytes()
            add_bytes(archive, f"penumbra-panel/{name}", content, 0o755 if name.endswith(".sh") else 0o644)
        for name, path in binaries.items():
            add_file(archive, path, f"penumbra-panel/bin/{name}")
        add_bytes(archive, "penumbra-panel/bundle.json", (json.dumps(bundle, indent=2) + "\n").encode())
    suffix = "" if release["cosmic_version"] == "1.10.0" else "-cosmic-" + release["cosmic_version"]
    source_archive = output / f"penumbra-panel-v{release['version']}{suffix}-source.tar.gz"
    prefix = f"penumbra-panel-v{release['version']}-source"
    with tarfile.open(source_archive, "w:gz") as archive:
        for key, source in sources.items():
            for path, relative in source_files(source):
                add_file(archive, path, f"{prefix}/{key}/{relative}")
            vendor = vendors[key]
            for path in sorted(vendor.rglob("*")):
                if path.is_file() or path.is_symlink():
                    add_file(archive, path, f"{prefix}/{key}/vendor/{path.relative_to(vendor).as_posix()}")
            add_bytes(archive, f"{prefix}/{key}/.cargo/config.toml", vendor_configs[key].read_bytes())
        for name in FILES:
            content = (json.dumps(release, indent=2) + "\n").encode() if name == "release.json" else (ROOT / name).read_bytes()
            add_bytes(archive, f"{prefix}/release-tools/{name}", content, 0o755 if name.endswith(".sh") else 0o644)
    checksum_file = output / "SHA256SUMS"
    records = {line.split()[1]: line.split()[0] for line in checksum_file.read_text().splitlines()} if checksum_file.exists() else {}
    records.update({path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (binary_archive, source_archive)})
    checksums = "".join(f"{checksum}  {name}\n" for name, checksum in sorted(records.items()))
    checksum_file.write_text(checksums)
    print(checksums, end="")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel-binary", type=Path, required=True)
    parser.add_argument("--settings-binary", type=Path, required=True)
    parser.add_argument("--panel-source", type=Path, required=True)
    parser.add_argument("--settings-source", type=Path, required=True)
    for key in ("panel", "settings"):
        parser.add_argument(f"--{key}-vendor", type=Path, required=True)
        parser.add_argument(f"--{key}-vendor-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cosmic-version", choices=("1.10.0", "1.11.0"), default="1.10.0")
    args = parser.parse_args()
    package({"cosmic-panel": args.panel_binary, "cosmic-settings": args.settings_binary},
            {"panel": args.panel_source, "settings": args.settings_source},
            {"panel": args.panel_vendor, "settings": args.settings_vendor},
            {"panel": args.panel_vendor_config, "settings": args.settings_vendor_config}, args.output,
            release_config.select(json.loads((ROOT / "release.json").read_text()), args.cosmic_version))


if __name__ == "__main__":
    main()
