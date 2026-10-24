"""Select the pinned source and binaries for an explicitly supported COSMIC release."""
import copy

import system_packages


def select(release, version=None):
    variants = release.get("supported_upstreams", {})
    if version is None:
        manager = system_packages.backend()
        versions = []
        for name in ("cosmic-panel", "cosmic-settings"):
            package = system_packages.query(name, manager)
            versions.append(system_packages.upstream_version(name, package))
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
