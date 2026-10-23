"""Select the pinned source and binaries for an explicitly supported COSMIC release."""
import copy
import re
import subprocess


def select(release, version=None):
    variants = release.get("supported_upstreams", {})
    if version is None:
        versions = []
        for name in ("cosmic-panel", "cosmic-settings"):
            try:
                package = subprocess.check_output(["pacman", "-Q", name], text=True, stderr=subprocess.PIPE).strip()
            except (OSError, subprocess.CalledProcessError) as error:
                raise RuntimeError("Cannot detect COSMIC. Use --cosmic-version for a build-only source build.") from error
            match = re.fullmatch(re.escape(name) + r" (?:[0-9]+:)?([0-9]+\.[0-9]+\.[0-9]+)-[^ ]+", package)
            if not match:
                raise RuntimeError("Unsupported package: " + package)
            versions.append(match[1])
        if len(set(versions)) != 1:
            raise RuntimeError("The installed Panel and Settings versions must match.")
        version = versions[0]
    if version not in variants:
        raise RuntimeError("Unsupported COSMIC version: " + version)
    selected = copy.deepcopy(release)
    selected["cosmic_version"] = version
    selected["upstreams"] = copy.deepcopy(variants[version])
    return selected


def asset(release):
    version = release["cosmic_version"]
    suffix = "" if version == "1.10.0" else "-cosmic-" + version
    return "penumbra-panel" + suffix + "-linux-x86_64.tar.gz"
