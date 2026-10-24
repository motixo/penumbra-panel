# Penumbra Panel

A softer edge for your COSMIC desktop. Penumbra replaces the panel's flat background with a gradient that fades into your wallpaper.

**Dark theme**

![Penumbra Panel and its settings in the dark theme](assets/screenshot-dark.png)

**Light theme**

![Penumbra Panel and its settings in the light theme](assets/screenshot-light.png)

## Features

- Gradient backgrounds for panels on the top, bottom, left, or right edge.
- Colors follow the panel's appearance, including light and dark themes.
- Gradient strength follows **Background opacity** in COSMIC Settings.
- Adaptive fade size: 32 px panel → 96 px gradient, 48 → 144, 64 → 192.
- Auto-hide moves and fades the background with the panel.
- A **Panel gradient** switch in Settings, independently for the panel and dock.

## Compatibility

This release supports **Arch Linux** and **Fedora 43 or newer** with COSMIC **1.10.0 or 1.11.0**. Panel and Settings must use the same upstream version.

Supported Arch package pairs:

| COSMIC | `cosmic-panel` | `cosmic-settings` |
| --- | --- | --- |
| 1.10.0 | `1:1.10.0-1` | `1:1.10.0-1` |
| 1.11.0 | `1:1.11.0-1` | `1:1.11.0-1` |

On Fedora, the installer queries the native RPM packages. Fedora package release suffixes such as `-2.fc43` are accepted; the launcher records each installed package’s exact epoch, version, release, and architecture. After either package changes, it selects the stock programs until you reinstall a compatible Penumbra release.

The installer detects the distribution and installed COSMIC version and selects its matching binaries. The same ready-made binaries support both distributions and require **Linux x86_64** and **glibc 2.42 or newer**. Source builds use the same pinned version with your local toolchain and libraries. Both versions passed the panel and Settings regression tests; gradient controls, themes, maximize/restore, all four edges, opacity and auto-hide were also exercised in isolated desktops.

Penumbra installs patched versions of both the panel and Settings for your user. The system packages stay in place. These are full programs, so another custom replacement for either program must be combined with these patches. Pulsar Clock remains a separate applet and can be used alongside Penumbra.

### Using Rasm and Pulsar

Pulsar Clock is a separate applet. Rasm has its own distribution requirements; the combined Settings binaries currently target Arch Linux. For Rasm's font controls on Arch, install Penumbra first and then install the matching [cosmic-rasm](https://github.com/motixo/cosmic-rasm) release. Rasm selects a combined Settings binary with both the font controls and **Panel gradient**. Its updated launcher falls back to Penumbra's saved launcher after a COSMIC version change.

When updating Penumbra while Rasm owns the Settings launcher, uninstall Rasm without `--purge`, update Penumbra, and reinstall Rasm. This keeps your font preferences and lets the installers preserve each other's launchers.

## Easy install: ready-made binaries

The installer needs `curl`, `tar`, and Python 3. On Fedora, install them with `sudo dnf install curl tar python3` if needed.

Download the binary archive from [Releases](https://github.com/motixo/penumbra-panel/releases/latest), or run:

```sh
curl -fLO https://github.com/motixo/penumbra-panel/releases/latest/download/penumbra-panel-linux-x86_64.tar.gz
tar -xzf penumbra-panel-linux-x86_64.tar.gz
cd penumbra-panel
./install.sh
```

Run as your normal desktop user, without `sudo`. The archive includes both compiled programs, the installer and the uninstaller. No Rust toolchain or local compilation is required.

The installer checks package versions, both binary checksums, and whether both programs can run before replacing a launcher. Existing preferences are preserved during updates. The default profile is `Panel`; select another existing profile with `--profile NAME`, or use `--no-activate` to keep every gradient preference unchanged.

**Log out and back in after installing**, then open:

**Settings → Desktop → Panel → Style → Panel gradient**

Use the same switch on the **Dock** page for the dock. Set **Gap** off and adjust **Background opacity** to change gradient strength. The switch and opacity changes apply immediately once the patched programs are running.

Your session's `PATH` must put `~/.local/bin` before `/usr/bin`, so COSMIC can find the local launchers. The installer reports when the current PATH needs adjustment. Installation leaves the running panel, applets, and settings daemon running.

## Build it yourself

On Fedora, install the build tools and development libraries:

```sh
sudo dnf install gcc gcc-c++ rust cargo git python3 clang cmake pkgconf-pkg-config \
  fontconfig-devel freetype-devel wayland-devel libxkbcommon-devel libinput-devel \
  pulseaudio-libs-devel pipewire-devel libglvnd-devel dbus-devel systemd-devel \
  libdav1d-devel openssl-devel binutils
```

On Arch:

```sh
sudo pacman -S --needed base-devel rust git python clang cmake pkgconf \
  fontconfig freetype2 wayland libxkbcommon libinput libpulse libpipewire \
  libglvnd dbus systemd-libs dav1d
```

Build and install:

```sh
git clone https://github.com/motixo/penumbra-panel.git
cd penumbra-panel
./install.sh --from-source
```

This downloads both upstream workspaces at the pinned commits matching COSMIC 1.10.0 or 1.11.0, checks and applies the patches, runs the regression tests, and builds optimized release binaries using their original `Cargo.lock` files. Installation begins only after both builds and runtime checks succeed.

To build without installing, or use fewer parallel jobs:

```sh
./install.sh --from-source --build-only
./install.sh --from-source --jobs 2
./install.sh --from-source --cosmic-version 1.11.0 --build-only
```

`--profile NAME` and `--no-activate` also work with source builds. Source and build files are kept under `~/.cache/penumbra-panel/`. Set an absolute `CARGO_TARGET_DIR` to reuse compiled dependencies across builds. Internet access is needed to fetch upstream sources and dependencies.

### Corresponding release source

Each release includes corresponding binary and source archives for both supported COSMIC versions. The default filenames target 1.10.0; the 1.11.0 filenames include `-cosmic-1.11.0`. The default binary installer can download the matching 1.11.0 archive automatically. Each source archive contains the exact patched Panel and Settings workspaces, their original license notices, vendored Cargo dependencies, and the release tools. To build from that archive, enter each workspace and run:

```sh
cd panel
cargo build --release --locked --offline -p cosmic-panel-bin
cd ../settings
cargo build --release --locked --offline -p cosmic-settings
```

The vendor configurations are included. A compatible Rust toolchain and system development libraries are still required.

## Update

Download and install the latest binary archive again. From a source checkout:

```sh
git pull --ff-only
./install.sh --from-source
```

Saved gradient settings, panel layout, opacity, applets, and clock preferences are preserved. The new programs load after logging out and back in. Reopen Settings to load its new executable.

After either supported COSMIC package changes, the launchers automatically select the stock programs on their next start. Use a compatible Penumbra release for the new COSMIC version; source builds also check the supported versions. This patch does not prevent system updates.

## Uninstall

```sh
./uninstall.sh
```

Then log out and back in and reopen Settings. This removes the local launchers and binaries, restoring the system programs. Gradient preferences remain for a later reinstall. To remove those too:

```sh
./uninstall.sh --purge
```

The uninstaller checks launcher ownership and preserves any replacement installed by another project.

## Installed files

| Purpose | Default location |
| --- | --- |
| Launchers | `~/.local/bin/cosmic-panel`, `~/.local/bin/cosmic-settings` |
| Binaries | `~/.local/share/penumbra-panel/versions/` |
| Installer state | `~/.local/state/penumbra-panel/` |
| Build cache | `~/.cache/penumbra-panel/` |
| Gradient preferences | `~/.config/cosmic/com.system76.CosmicPanel.PROFILE/v1/top_edge_gradient` |

Data, state, configuration, and cache respect their XDG environment variables. The preference key keeps its earlier name for compatibility with the original local patch. The installer can replace that patch's managed launchers while retaining its preferences.

## Development

```sh
python3 -m unittest discover -s tests -v
bash -n install.sh uninstall.sh build-from-source.sh
python3 scripts/build_release.py ./dist
```

The release command builds and tests both programs, vendors their dependencies, and produces binary and source archives with `SHA256SUMS`. The **Build binary release** GitHub Actions workflow builds on Fedora 43 for the older glibc baseline, checks the binaries and isolated install/uninstall lifecycle on Fedora 43, 44, 45 and Arch Linux, and publishes the version from `release.json`.

The rendering surface has an empty input region, so the gradient does not intercept clicks outside the panel. The fade follows the panel's edge, size, output scale, and auto-hide motion. Maximized behavior follows COSMIC's existing window detection; keep `keep_style_on_maximize` disabled to use the uniform maximized background.

## License and upstream

[GPL-3.0-only](LICENSE). Based on [COSMIC Panel](https://github.com/pop-os/cosmic-panel) and [COSMIC Settings](https://github.com/pop-os/cosmic-settings) by System76 and their contributors. See [NOTICE](NOTICE) for the exact upstream commits and attribution. This is an independent customization.
