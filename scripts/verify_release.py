#!/usr/bin/env python3
"""Exercise release binaries and an isolated installation against native packages."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile

import install_prebuilt
import panel_control as manager
import release_config
import system_packages


def verify(archives):
    reports = []
    installed = False
    for archive in archives:
        with tempfile.TemporaryDirectory(prefix="penumbra-release-check-") as temporary:
            work = Path(temporary)
            work.chmod(0o755)
            with tarfile.open(archive) as stream:
                stream.extractall(work, filter="data")
            root = work / "penumbra-panel"
            release = json.loads((root / "release.json").read_text())
            # Both upstream versions must execute, even when only one is installed.
            install_prebuilt.check_platform(release, packages=False)
            binaries = {name: root / "bin" / name for name in manager.PROGRAMS}
            bundle = json.loads((root / "bundle.json").read_text())
            install_prebuilt.check_bundle(binaries, bundle, release)
            for binary in binaries.values():
                dependencies = subprocess.check_output(["ldd", str(binary)], text=True)
                if "not found" in dependencies:
                    raise RuntimeError(dependencies)
            native = release_config.select(release)
            report = {"archive": archive.name, "backend": system_packages.backend(),
                      "cosmic": release["cosmic_version"], "runtime": "passed"}
            if native["cosmic_version"] == release["cosmic_version"]:
                home = work / "user"
                profile = home / ".config/cosmic/com.system76.CosmicPanel.Panel/v1"
                profile.mkdir(parents=True)
                (profile / "anchor").write_text("Top")
                (profile / "opacity").write_text("0.67")
                preference = profile / "top_edge_gradient"
                saved = "Some((enabled: false, height: 120, maximized_opacity: 0.96))\n"
                preference.write_text(saved)
                identity = {}
                if os.geteuid() == 0:
                    # CI containers run as root; the public installer must run as a user.
                    identity = {"user": 1000, "group": 1000}
                    for path in [home, *home.rglob("*")]:
                        os.chown(path, 1000, 1000)
                env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
                           XDG_DATA_HOME=str(home / ".local/share"), XDG_STATE_HOME=str(home / ".local/state"),
                           XDG_CACHE_HOME=str(home / ".cache"))
                subprocess.run([str(root / "install.sh")], cwd=root, env=env, check=True, **identity)
                for name in manager.PROGRAMS:
                    binary = home / ".local/bin" / name
                    version = subprocess.check_output([str(binary), "--version"], env=env, text=True, **identity).strip()
                    if version != bundle["binaries"][name]["version"]:
                        raise RuntimeError("The native package guard selected the stock program.")
                subprocess.run([str(root / "uninstall.sh")], cwd=root, env=env, check=True, **identity)
                if preference.read_text() != saved or (profile / "opacity").read_text() != "0.67":
                    raise RuntimeError("Installation changed saved preferences.")
                if any((home / ".local/bin" / name).exists() for name in manager.PROGRAMS):
                    raise RuntimeError("Uninstall left a launcher behind.")
                installed = True
                report["install_uninstall"] = "passed"
            reports.append(report)
    if not installed:
        raise RuntimeError("No release archive matches the native COSMIC packages.")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", type=Path, nargs="+")
    verify(parser.parse_args().archives)
