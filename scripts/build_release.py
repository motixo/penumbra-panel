#!/usr/bin/env python3
"""Build, test and package a Linux binary release and its source."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

import build_source
import package_release
import release_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--jobs", type=int, default=int(os.environ.get("CARGO_BUILD_JOBS", "2")))
    parser.add_argument("--cosmic-version", choices=("1.10.0", "1.11.0"), default="1.10.0")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    root = Path(__file__).resolve().parents[1]
    release = release_config.select(json.loads((root / "release.json").read_text()), args.cosmic_version)
    # Workspaces remain available for release inspection and later rebuilds.
    cache = root / ".build"
    cache.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="release-", dir=cache))
    sources, binaries, _ = build_source.build(root, work, release, args.jobs)
    vendors, configs = {}, {}
    # Each workspace resolves different git revisions with identical package
    # versions, so keep their vendor sources and replacement tables separate.
    for key, source in sources.items():
        vendor = work / ("vendor-" + key)
        config = work / ("vendor-" + key + ".toml")
        with config.open("w") as stream:
            subprocess.run(["cargo", "vendor", "--locked", "--versioned-dirs", str(vendor)],
                           cwd=source, stdout=stream, check=True)
        original_config = source / ".cargo/config.toml"
        original = original_config.read_text() + "\n" if original_config.is_file() else ""
        config.write_text(original + config.read_text().replace(str(vendor), "vendor"))
        vendors[key], configs[key] = vendor, config
    package_release.package(binaries, sources, vendors, configs, args.output.resolve(), release)


if __name__ == "__main__":
    main()
