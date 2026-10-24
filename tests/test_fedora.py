import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import panel_control as manager
import release_config
import system_packages
import test_installer


class DistributionTests(unittest.TestCase):
    def test_fedora_uses_rpm_even_when_pacman_is_also_installed(self):
        with patch.object(system_packages.platform, "freedesktop_os_release", return_value={"ID": "fedora", "VERSION_ID": "43"}):
            self.assertEqual(system_packages.backend(), "rpm")

    def test_arch_and_arch_derivatives_keep_pacman(self):
        for release in ({"ID": "arch"}, {"ID": "endeavouros", "ID_LIKE": "arch"}):
            with patch.object(system_packages.platform, "freedesktop_os_release", return_value=release):
                self.assertEqual(system_packages.backend(), "pacman")

    def test_other_rpm_distributions_are_not_assumed_to_be_fedora(self):
        with patch.object(system_packages.platform, "freedesktop_os_release", return_value={"ID": "rhel", "ID_LIKE": "fedora"}):
            with self.assertRaisesRegex(RuntimeError, "Arch Linux and Fedora"):
                system_packages.backend()

    def test_rpm_query_includes_epoch_release_and_architecture(self):
        package = "cosmic-panel 0:1.11.0-2.fc44.x86_64"
        with patch.object(system_packages.subprocess, "check_output", return_value=package + "\n") as query:
            self.assertEqual(system_packages.query("cosmic-panel", "rpm"), package)
        self.assertEqual(query.call_args.args[0], ["rpm", "-q", "--qf", "%{NAME} %{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}\\n", "cosmic-panel"])

    def test_failed_query_does_not_install_or_guess_a_version(self):
        with patch.object(system_packages.subprocess, "check_output", side_effect=subprocess.CalledProcessError(1, "rpm")):
            with self.assertRaisesRegex(RuntimeError, "Install the native COSMIC packages"):
                system_packages.query("cosmic-panel", "rpm")

    def test_prerelease_and_multiple_architectures_are_rejected(self):
        for package in ("cosmic-panel 0:1.11.0~beta-1.fc43.x86_64", "cosmic-panel 0:1.11.0-1.fc43.x86_64\ncosmic-panel 0:1.11.0-1.fc43.i686"):
            with self.assertRaisesRegex(RuntimeError, "Unsupported package"):
                system_packages.upstream_version("cosmic-panel", package)


class FedoraInstallerTests(test_installer.InstallerTests):
    # Run the existing lifecycle and rollback cases on the RPM launcher as well.
    def setUp(self):
        super().setUp()
        self.backend_mock.return_value = "rpm"
        self.packages = {name: name + " 0:1.10.0-2.fc43.x86_64" for name in manager.PROGRAMS}

    def test_launcher_uses_stock_program_after_package_upgrade(self):
        self.install()
        state = json.loads((manager.STATE / "install.json").read_text())
        active = Path(state["directory"]) / "cosmic-settings"
        active.write_text('#!/bin/sh\nprintf "patched:%s\\n" "$1"\n')
        active.chmod(0o755)
        fake = self.root / "fakebin"
        fake.mkdir()
        rpm = fake / "rpm"
        rpm.write_text('#!/bin/sh\n[ "$1" = "-q" ] && [ "$2" = "--qf" ] || exit 2\n'
                       'case "$4" in cosmic-panel|cosmic-settings) ;; *) exit 3 ;; esac\n'
                       '[ "${RPM_MISSING:-0}" = 0 ] || exit 1\n'
                       'printf "%s %s\\n" "$4" "${RPM_PACKAGE:-0:1.10.0-2.fc43.x86_64}"\n')
        rpm.chmod(0o755)
        stock = self.root / "stock-settings"
        stock.write_text('#!/bin/sh\nprintf "stock:%s\\n" "$1"\n')
        stock.chmod(0o755)
        wrapper = manager.BIN / "cosmic-settings"
        import shlex
        wrapper.write_text(wrapper.read_text().replace("/usr/bin/cosmic-settings", shlex.quote(str(stock))))
        env = dict(os.environ, PATH=str(fake) + ":" + os.environ["PATH"])
        run = lambda: subprocess.check_output([str(wrapper), "argument with spaces"], env=env, text=True)
        self.assertEqual(run(), "patched:argument with spaces\n")
        for version in ("0:1.10.0-3.fc43.x86_64", "1:1.10.0-2.fc43.x86_64", "0:1.11.0-2.fc43.x86_64"):
            env["RPM_PACKAGE"] = version
            self.assertEqual(run(), "stock:argument with spaces\n")
        env.pop("RPM_PACKAGE")
        env["RPM_MISSING"] = "1"
        self.assertEqual(run(), "stock:argument with spaces\n")

    def test_native_fedora_rebuilds_are_accepted_and_exactly_recorded(self):
        for version in ("1.10.0", "1.11.0"):
            release = release_config.select(self.release, version)
            packages = {name: f"{name} 0:{version}-3.fc44.x86_64" for name in manager.PROGRAMS}
            with patch.object(system_packages.subprocess, "check_output", side_effect=lambda args, **kwargs: packages[args[-1]] + "\n"):
                self.assertEqual(manager.package_versions(release), packages)
                self.assertEqual(release_config.select(self.release)["cosmic_version"], version)

    def test_unsupported_native_version_is_rejected_before_writes(self):
        with patch.object(system_packages.subprocess, "check_output", return_value="cosmic-panel 0:1.12.0-1.fc45.x86_64\n"):
            with self.assertRaisesRegex(RuntimeError, "Unsupported package"):
                manager.install(self.binaries, self.bundle, self.release)
        self.assertFalse(manager.DATA.exists())
        self.assertFalse(manager.STATE.exists())


if __name__ == "__main__":
    unittest.main()
