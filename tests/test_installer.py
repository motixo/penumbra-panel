import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import install_prebuilt as installer
import panel_control as manager
import release_config
import system_packages


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="penumbra test ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.backend = patch.object(system_packages, "backend", return_value="pacman")
        self.backend_mock = self.backend.start()
        self.addCleanup(self.backend.stop)
        self.release = json.loads((ROOT / "release.json").read_text())
        self.locations = dict(DATA=self.root / "data", STATE=self.root / "state",
                              CONFIG=self.root / "config", BIN=self.root / "bin")
        self.paths = patch.multiple(manager, **self.locations)
        self.paths.start()
        self.addCleanup(self.paths.stop)
        self.profile = manager.preference_file("Panel").parent
        self.profile.mkdir(parents=True)
        (self.profile / "anchor").write_text("Top")
        (self.profile / "opacity").write_text("0.67")
        self.packages = {c["binary"]: c["package"] for c in self.release["upstreams"].values()}
        self.binaries = {}
        for name in manager.PROGRAMS:
            path = self.root / (name + "-build")
            path.write_bytes(b"\x7fELF" + name.encode())
            path.chmod(0o755)
            self.binaries[name] = path
        self.bundle = {**self.release, "binaries": {
            name: {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                   "version": f"{name} {self.release['cosmic_version']} + penumbra-panel {self.release['version']}"}
            for name, path in self.binaries.items()}}

    def install(self, **kwargs):
        with patch.object(manager, "package_versions", return_value=self.packages):
            manager.install(self.binaries, self.bundle, self.release, **kwargs)

    def archive(self, entries=None):
        destination = self.root / installer.ASSET
        if entries is None:
            entries = [("penumbra-panel/bundle.json", json.dumps(self.bundle).encode())]
            entries += [("penumbra-panel/bin/" + name, path.read_bytes()) for name, path in self.binaries.items()]
        with tarfile.open(destination, "w:gz") as archive:
            for name, content in entries:
                if isinstance(content, tarfile.TarInfo):
                    archive.addfile(content)
                else:
                    info = tarfile.TarInfo(name)
                    info.size = len(content)
                    archive.addfile(info, io.BytesIO(content))
        return destination

    def test_install_and_uninstall_preserve_panel_settings_and_preferences(self):
        self.install()
        self.assertEqual((self.profile / "opacity").read_text(), "0.67")
        self.assertIn("enabled: true", (self.profile / "top_edge_gradient").read_text())
        state = json.loads((manager.STATE / "install.json").read_text())
        for name in manager.PROGRAMS:
            self.assertTrue((manager.BIN / name).stat().st_mode & 0o111)
            self.assertEqual((Path(state["directory"]) / name).read_bytes(), self.binaries[name].read_bytes())
        manager.uninstall()
        self.assertFalse((manager.BIN / "cosmic-panel").exists())
        self.assertFalse((manager.BIN / "cosmic-settings").exists())
        self.assertFalse(manager.DATA.exists())
        self.assertFalse((manager.STATE / "install.json").exists())
        self.assertTrue((self.profile / "top_edge_gradient").exists())
        self.assertEqual((self.profile / "opacity").read_text(), "0.67")

    def test_update_preserves_disabled_state_and_custom_values(self):
        saved = "Some((enabled: false, height: 173, opacity: 0.48, maximized_opacity: 0.87))\n"
        (self.profile / "top_edge_gradient").write_text(saved)
        self.install()
        self.install()
        self.assertEqual((self.profile / "top_edge_gradient").read_text(), saved)

    def test_no_activate_keeps_missing_preference_missing(self):
        self.install(activate=False)
        self.assertFalse((self.profile / "top_edge_gradient").exists())

    def test_each_profile_is_independent(self):
        dock = manager.preference_file("Dock").parent
        dock.mkdir(parents=True)
        (dock / "anchor").write_text("Right")
        self.install(profile="Dock")
        self.assertTrue((dock / "top_edge_gradient").exists())
        self.assertFalse((self.profile / "top_edge_gradient").exists())

    def test_foreign_settings_launcher_blocks_all_writes(self):
        manager.BIN.mkdir()
        foreign = manager.BIN / "cosmic-settings"
        foreign.write_text("#!/bin/sh\n# Another project\n")
        with self.assertRaisesRegex(ValueError, "different override"):
            self.install()
        self.assertFalse(manager.DATA.exists())
        self.assertFalse(manager.STATE.exists())
        self.assertFalse((manager.BIN / "cosmic-panel").exists())
        self.assertEqual(foreign.read_text(), "#!/bin/sh\n# Another project\n")

    def test_symlink_launcher_is_preserved(self):
        manager.BIN.mkdir()
        target = self.root / "original"
        target.write_text("original")
        (manager.BIN / "cosmic-panel").symlink_to(target)
        with self.assertRaises(ValueError):
            self.install()
        self.assertEqual(target.read_text(), "original")
        self.assertFalse(manager.DATA.exists())

    def test_original_local_patch_can_be_migrated_without_losing_preferences(self):
        manager.BIN.mkdir()
        for name in manager.PROGRAMS:
            (manager.BIN / name).write_text("#!/bin/sh\n" + manager.LEGACY_MARKER + "\n")
        saved = "Some((enabled: true, height: 96, maximized_opacity: 0.96))"
        (self.profile / "top_edge_gradient").write_text(saved)
        self.install()
        self.assertEqual((self.profile / "top_edge_gradient").read_text(), saved)
        self.assertIn(manager.MARKER, (manager.BIN / "cosmic-settings").read_text())

    def test_failed_second_launcher_write_rolls_back_the_first_and_preferences(self):
        original_atomic = manager.atomic
        rejected = []
        def fail_once(path, content, mode=0o600):
            if path == manager.BIN / "cosmic-settings" and not rejected:
                rejected.append(path)
                raise OSError("simulated write failure")
            return original_atomic(path, content, mode)
        with patch.object(manager, "atomic", side_effect=fail_once):
            with self.assertRaisesRegex(OSError, "simulated write failure"):
                self.install()
        self.assertFalse((manager.BIN / "cosmic-panel").exists())
        self.assertFalse((manager.BIN / "cosmic-settings").exists())
        self.assertFalse((manager.STATE / "install.json").exists())
        self.assertFalse((self.profile / "top_edge_gradient").exists())

    def test_uninstall_preserves_a_new_foreign_override(self):
        self.install()
        foreign = manager.BIN / "cosmic-settings"
        foreign.write_text("new owner\n")
        with self.assertRaises(ValueError):
            manager.uninstall()
        self.assertTrue((manager.BIN / "cosmic-panel").exists())
        self.assertEqual(foreign.read_text(), "new owner\n")
        self.assertTrue(manager.DATA.exists())

    def test_purge_removes_gradient_preferences_for_panel_and_dock(self):
        self.install()
        dock = manager.preference_file("Dock")
        dock.parent.mkdir(parents=True)
        dock.write_text("None")
        manager.uninstall(purge=True)
        self.assertFalse(manager.preference_file("Panel").exists())
        self.assertFalse(dock.exists())
        self.assertFalse(manager.STATE.exists())

    def test_package_mismatch_is_rejected_before_installation(self):
        with patch.object(manager.subprocess, "check_output", return_value="cosmic-panel 1:2.0.0-1\n"):
            with self.assertRaisesRegex(RuntimeError, "Unsupported package"):
                manager.install(self.binaries, self.bundle, self.release)
        self.assertFalse(manager.DATA.exists())
        self.assertFalse(manager.STATE.exists())

    def test_launcher_uses_stock_program_after_package_upgrade(self):
        self.install()
        state = json.loads((manager.STATE / "install.json").read_text())
        active = Path(state["directory"]) / "cosmic-settings"
        active.write_text("#!/bin/sh\nprintf 'patched\\n'\n")
        active.chmod(0o755)
        fake = self.root / "fakebin"
        fake.mkdir()
        pacman = fake / "pacman"
        pacman.write_text('#!/bin/sh\nprintf "%s %s\\n" "$2" "${PENUMBRA_TEST_VERSION:-1:1.10.0-1}"\n')
        pacman.chmod(0o755)
        stock = self.root / "stock-settings"
        stock.write_text("#!/bin/sh\nprintf 'stock\\n'\n")
        stock.chmod(0o755)
        wrapper = manager.BIN / "cosmic-settings"
        wrapper.write_text(wrapper.read_text().replace("/usr/bin/cosmic-settings", "'" + str(stock) + "'"))
        env = dict(os.environ, PATH=str(fake) + ":" + os.environ["PATH"])
        self.assertEqual(subprocess.check_output([str(wrapper)], env=env, text=True), "patched\n")
        env["PENUMBRA_TEST_VERSION"] = "1:2.0.0-1"
        self.assertEqual(subprocess.check_output([str(wrapper)], env=env, text=True), "stock\n")

    def test_archive_checksum_and_safe_unpack(self):
        archive = self.archive()
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        installer.verify_checksum(archive, f"{checksum}  {archive.name}\n")
        destination = self.root / "unpacked"
        destination.mkdir()
        binaries, bundle = installer.unpack(archive, destination)
        self.assertEqual(bundle, self.bundle)
        self.assertEqual(binaries["cosmic-panel"].read_bytes(), self.binaries["cosmic-panel"].read_bytes())
        with self.assertRaises(RuntimeError):
            installer.verify_checksum(archive, "0" * 64 + "  " + archive.name)

    def test_link_or_duplicate_member_cannot_replace_a_binary(self):
        link = tarfile.TarInfo("penumbra-panel/bin/cosmic-panel")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../outside"
        base = [("penumbra-panel/bundle.json", json.dumps(self.bundle).encode())]
        for entries in [base + [(link.name, link)], base + [base[0]]]:
            archive = self.archive(entries)
            with self.assertRaises(RuntimeError):
                installer.unpack(archive, self.root)
        self.assertFalse((self.root / "outside").exists())

    def test_runtime_failure_of_either_binary_blocks_installation(self):
        def runtime(command, **kwargs):
            name = Path(command[0]).name.removesuffix("-build")
            return subprocess.CompletedProcess(command, 1 if name == "cosmic-settings" else 0,
                self.bundle["binaries"][name]["version"] + "\n", "missing shared library")
        with patch.object(installer.subprocess, "run", side_effect=runtime):
            with self.assertRaisesRegex(RuntimeError, "cosmic-settings cannot run"):
                installer.check_bundle(self.binaries, self.bundle, self.release)
        self.assertFalse(manager.DATA.exists())

    def test_tampered_binary_is_rejected_before_execution(self):
        self.binaries["cosmic-panel"].write_bytes(b"modified")
        with patch.object(installer.subprocess, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "Checksum mismatch"):
                installer.check_bundle(self.binaries, self.bundle, self.release)
            run.assert_not_called()

    def test_download_failure_keeps_existing_installation(self):
        self.install()
        before = {name: (manager.BIN / name).read_bytes() for name in manager.PROGRAMS}
        with patch.object(release_config, "select", return_value=self.release), patch.object(installer, "check_platform"), patch.object(installer, "fetch", side_effect=OSError("network unavailable")):
            with self.assertRaisesRegex(OSError, "network unavailable"):
                installer.install_release(ROOT)
        for name in manager.PROGRAMS:
            self.assertEqual((manager.BIN / name).read_bytes(), before[name])

    def test_invalid_or_missing_profile_has_no_side_effects(self):
        for name in ("../Panel", "missing", "Panel/../Dock"):
            with self.assertRaises(ValueError):
                self.install(profile=name)
        self.assertFalse(manager.DATA.exists())
        self.assertFalse(manager.STATE.exists())

    def test_supported_version_selects_matching_source_and_archive(self):
        for version in ("1.10.0", "1.11.0"):
            with patch.object(system_packages.subprocess, "check_output", side_effect=lambda args, **kwargs: args[-1] + " 1:" + version + "-1\n"):
                release = release_config.select(self.release)
            self.assertEqual(release["cosmic_version"], version)
            self.assertEqual(release["upstreams"]["panel"]["ref"], "epoch-" + version)
            if version == "1.11.0":
                self.assertIn("1.11.0", release_config.asset(release))
        self.assertEqual(self.release["cosmic_version"], "1.10.0")

    def test_different_panel_and_settings_versions_are_rejected(self):
        with patch.object(system_packages.subprocess, "check_output", side_effect=["cosmic-panel 1:1.11.0-1\n", "cosmic-settings 1:1.10.0-1\n"]):
            with self.assertRaisesRegex(RuntimeError, "must match"):
                release_config.select(self.release)
        with self.assertRaisesRegex(RuntimeError, "Unsupported COSMIC"):
            release_config.select(self.release, "1.12.0")

    def test_other_version_archive_downloads_matching_binaries(self):
        package = self.root / "extracted"
        package.mkdir()
        (package / "release.json").write_text(json.dumps(self.release))
        (package / "bundle.json").write_text(json.dumps(self.bundle))
        selected = release_config.select(self.release, "1.11.0")
        matching = {**self.bundle, **selected}
        with patch.object(release_config, "select", return_value=selected), patch.object(installer, "check_platform"), patch.object(installer, "fetch", return_value=(self.binaries, matching)) as fetch, patch.object(installer, "check_bundle"), patch.object(manager, "install") as install:
            installer.install_release(package)
        self.assertEqual(fetch.call_args.args[0]["cosmic_version"], "1.11.0")
        self.assertEqual(install.call_args.args[2]["cosmic_version"], "1.11.0")


if __name__ == "__main__":
    unittest.main()
