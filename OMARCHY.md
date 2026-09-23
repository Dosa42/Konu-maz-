# Private Omarchy custom ISO build

This repository contains a manual GitHub Actions workflow and pinned source checkouts for building an actual x86_64 Omarchy installation ISO. The repository is private. The workflow stores artifacts in this repository and does not publish releases, Pages, containers, or a download website.

**Current stage: restore the disk installer while keeping all existing login facilities and local account records removed, including root and system accounts. No replacement login is installed.** The live image starts the installer directly on tty1 through systemd. The completed disk installation is finalized with the same account/login removal policy and uses `multi-user.target`, without a desktop or login session. The live status is embedded at `/usr/share/omarchy-iso/custom-build-status.json` and recorded in the build manifest. This is not a completed signer-only installation image.

## Start the ISO build

Open **Actions → Build private Omarchy custom ISO → Run workflow → main**. The workflow runs only when manually dispatched. No personal access token or repository secret is needed for the current upstream source downloads.

The job uses an Ubuntu 24.04 x86_64 runner, a privileged Arch Linux container pinned by digest, and the real upstream `mkarchiso` build. It builds the local Omarchy runtime/settings packages, constructs the offline installation package repository and creates the ISO. The job does not boot a virtual machine or exercise a physical USB token.

Artifacts retained for seven days:

- `omarchy-custom-development-iso-*`: ISO, SHA256, El Torito boot catalogue, build manifest, builder image identity, and selected package inventories.
- `pinned-offline-packages.json` inside the ISO artifact records explicitly pinned upstream archives, their verified checksums, identity and dependencies.
- `omarchy-effective-sources-*`: actual checked-out source files after patches/overlays, when selected. Git object stores are omitted; use the repository and preparation script to reconstruct buildable clones.
- `omarchy-build-logs-*`: host setup, complete build output, exact source identities and applied diffs, including on failure.

A successful job requires the real builder to return success and exactly one nonempty ISO with a readable El Torito boot catalogue. This is not a VM boot test or a claim that signer login works.

## Source layout

| Path | Purpose |
|---|---|
| `config/sources.lock.json` | Exact Omarchy, ISO, package and Archiso commits; immutable Arch image; pinned Node release/checksum. |
| `sources/omarchy` | Omarchy runtime source, recorded as a Git submodule link. |
| `sources/omarchy-iso` | Installer and Archiso build source. |
| `sources/omarchy-pkgs` | Local package recipes. |
| `patches/series.json` | Explicit ordered patches per source repository. |
| `patches/<source>/*.patch` | Tracked modifications to existing upstream files. |
| `overlays/<source>/` | Additional or replacement source files, preserving relative paths and executable permissions. |
| `scripts/prepare-sources.py` | Creates real standalone Git clones, checks their pins, applies patches and overlays, records source state. |
| `scripts/prepare-build-host.sh` | Prepares host tools and reports real Docker/storage availability. |
| `scripts/build-iso.sh` | Builds the ISO with logs, source archive, checksum and boot catalogue inspection. |
| `scripts/write-build-manifest.py` | Records actual output and dependency identities after the build. |
| `docs/USB_SIGNER_INTEGRATION.md` | Remaining concrete authentication integration work. |

Clone the build repository **without `--recurse-submodules`**, then run:

```bash
python3 scripts/prepare-sources.py
```

The preparation script clones the linked sources as standalone repositories with real `.git` directories. This is deliberate: Omarchy's dev PKGBUILDs copy the source directory, including Git metadata, into their build directory to calculate the package version. A conventional submodule `.git` pointer would point outside that copied directory. The nested Archiso dependency uses its official GitHub mirror at the exact commit recorded by the ISO source.

Inside the build container, root first copies the read-only Omarchy source into a temporary directory and transfers ownership of that copy to the unprivileged package builder. This preserves owner-only Git metadata such as partial-clone `.promisor` files, while leaving the host checkout's ownership and permissions unchanged. Both dev PKGBUILDs use this staged source through `OMARCHY_SRC`.

The script preserves local source changes on the pinned HEAD. It refuses to reset an existing different HEAD or delete an existing source directory. Overlays explicitly replace their corresponding target files. Repeating the command reports already-applied patches; an incompatible patch fails visibly.

## Keep custom changes in this repository

For an existing source file, edit its local checkout and save the incremental diff as an additional patch under `patches/<source>/`. Add its filename to that source's ordered array in `patches/series.json`. Do not save a second patch that repeats changes already present in an earlier patch. New files can be placed directly under `overlays/<source>/` at their required source-relative path. GitHub Actions only receives tracked changes; local uncommitted edits inside a source checkout are not transferred by pushing the build repository alone.

The supplied patches make the builder accept immutable image/Node inputs and unique output directories, use a pinned LazyVim starter revision, propagate a failed Neovim build command, identify the ISO as a development build, and integrate additional local packages. The removal and installer patches implement the stage described in [NO_LOGIN_STAGE.md](docs/NO_LOGIN_STAGE.md).

### Firmware removed from an upstream package index

The arch-mact2 package index no longer contains `apple-bcm-firmware`, which this pinned Omarchy source still requires for T2 Macs. The maintainer still publishes the original `14.0-1` archive. `overlays/omarchy-iso/builder/pinned-offline-packages.json` pins that exact HTTPS download and SHA-256. The builder verifies the bytes and `.PKGINFO`, adds the archive to the offline mirror, resolves its declared dependencies, excludes its name from online downloads, and retains its exact output during pruning. Firmware remains available offline; no macOS-dependent fetcher is substituted. An unavailable or mismatched pinned archive fails visibly.

Upstream evidence: [maintainer release](https://github.com/NoaHimesaka1873/arch-mact2-mirror/releases/tag/release), [new fetcher introduction](https://github.com/NoaHimesaka1873/arch-mact2-PKGBUILDs/commit/019d2f2516d36c14f3330384d25fa9f8c8e71c43).

### Neovim plugin cache

The Ristretto/Monokai plugin now comes from its available upstream `loctvl842/monokai-pro.nvim`; the previously configured `gthelding` repository returned an authentication error. The package runs a synchronous Lazy sync and checks missing plugins, failed tasks and Neovim errors before packaging. A failed plugin download now returns a failing build status instead of allowing `:qa!` to report success with an incomplete cache.

## Add an actual local signer package

1. Put its real `PKGBUILD` and associated source files in `overlays/omarchy-pkgs/pkgbuilds/<package-name>/`.
2. Add its exact package name to `overlays/omarchy-iso/builder/custom-local.packages`.
3. Add any additional builder dependencies to `overlays/omarchy-iso/builder/custom-build-dependencies.packages`.
4. If a local library is needed while compiling a later local package, put that provider before its consumers in `custom-local.packages` and also list it in `custom-build-install.packages`. It is then installed into the builder after compilation. Keep final authentication-policy packages out of this builder-only list.
5. Add the reviewed Omarchy/installer authentication changes as tracked patches or overlays.

Every name in `custom-local.packages` is built locally and installed in **both the live ISO and the target installation**. The builder keeps the exact local artifact, excludes it from online package replacement, includes its declared runtime dependencies in the offline mirror and checks the final target dependency resolution. Use one unsplit package name per recipe/list entry. Custom build dependencies must be available in the configured Arch/Omarchy repositories or explicitly provided by an additional build integration.

The custom package list is currently empty because no matching USB/PAM implementation has been established. No dummy signer, fabricated USB protocol, permissive authentication module or success stub is included.

## Build locally

Install and start Docker Engine on a Linux x86_64 host, then:

```bash
./scripts/prepare-build-host.sh
./scripts/build-iso.sh
```

Host tools include Git, curl, jq, Python 3, rsync, zstd and xorriso. The Arch container installs Archiso, the compiler/binutils/make toolchain, GRUB, image/package tools and the upstream Node/Neovim build dependencies. Additional PAM/USB development dependencies already listed are CMake, Ninja, pkgconf, Python, libusb, PAM and OpenSSL.

The build needs network access to fetch source and packages. The live installer uses the bundled offline package archives for a real disk installation, including hardware configuration and Limine/UKI generation. The archives contain upstream account/login files; a final installation phase removes those files and account records from the target before completion. No first-owner setup or autologin is staged. Source/image/Node versions are pinned; rolling Arch/Omarchy package repositories and LazyVim's plugin resolution still prevent a claim of byte-for-byte reproducibility. Actual selected package names and versions are saved with each output.

The ISO plus package mirror/container layers need substantial disk space. Host setup reports the actual available storage; 35 GiB is an advisory budget, not an enforced estimate. Only on disposable GitHub-hosted runners does it remove the explicitly listed unrelated preinstalled Android/Haskell/.NET/CodeQL directories. It does not perform that cleanup on a local or self-hosted machine.

## Scope of the current result

The live wizard asks for keyboard, hostname, timezone and disk layout. Optional disk encryption uses an explicitly chosen LUKS passphrase; this unlocks storage and does not create a root or user password. Cancellation or failure returns to fixed retry/reboot/power-off controls, without a shell. Retrying opens the wizard and disk confirmation again.

Linux numeric UID 0 remains available to PID 1 and the installer; no local root or system-account record is restored. Successful source checks or ISO creation do not establish that the installer or resulting system boots. The USB device protocol, key enrollment and authentication integration remain separate work before an image can be described as signer-only. The implementation map is in `docs/Omarchy_USB_signer_exacte_bronbestanden.md`.
