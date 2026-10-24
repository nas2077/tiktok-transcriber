# Releases

The source repository contains no executable, virtual environment, model weights,
downloaded user media, or build cache. Download runnable packages from
[GitHub Releases](https://github.com/nas2077/tiktok-transcriber/releases).

## Packages

| System | Files |
|---|---|
| Windows 10/11 x64 | `TikTok-Transcriber-<version>-windows-x64-setup.exe` (per-user installer), `TikTok-Transcriber-<version>-windows-x64.zip` (portable) |
| macOS 11+ | `TikTok-Transcriber-<version>-macos-arm64.dmg` (Apple silicon), `TikTok-Transcriber-<version>-macos-x64.dmg` (Intel) |
| Linux x86_64 / aarch64 | `.AppImage`, `.tar.gz`, `.deb`, `.rpm`, Arch `.pkg.tar.zst`; Flatpak bundle for x86_64 |
| Any system with Python 3.11+ | `tiktok_transcriber-<version>-py3-none-any.whl` and the source archive |

Linux x86_64 packages are built on Ubuntu 22.04 and need glibc 2.35 or newer
(Ubuntu 22.04, Debian 12, Fedora 36, RHEL/Rocky/Alma 10 or newer; RHEL 9 has
glibc 2.34 and needs the Flatpak). Linux aarch64
packages are built on Ubuntu 24.04, because Qt publishes its ARM wheels for glibc
2.39 only: Ubuntu 24.04, Debian 13 (and Raspberry Pi OS based on it), Fedora 40
or newer. The x86_64 Flatpak carries its own runtime and also works on older or
immutable systems. The Intel Mac build uses onnxruntime 1.23.2, its last release
with Intel Mac wheels.

Nothing is signed with a publisher certificate. Windows SmartScreen may warn, and
macOS asks the first time: open System Settings > Privacy & Security and choose
"Open Anyway". Checksums provide integrity checking, not a publisher identity.

## Verify a download

Download the package and `SHA256SUMS.txt` from the same release, then compare:

```powershell
Get-FileHash .\TikTok-Transcriber-0.2.2-windows-x64-setup.exe -Algorithm SHA256
```

```bash
sha256sum --ignore-missing -c SHA256SUMS.txt     # Linux
shasum -a 256 --ignore-missing -c SHA256SUMS.txt # macOS
```

`install.sh` and `install.ps1` perform this check before installing anything.

## Build

Windows, in PowerShell (`-Installer` needs Inno Setup 6):

```powershell
powershell -ExecutionPolicy Bypass -File dev\build.ps1 -Quiet -Installer
```

The script creates/uses `dev/.venv`, installs constrained dependencies, verifies
the media inputs, installs the LGPL PyAV variant, collects license texts, and
builds with PyInstaller. Output goes to `dev/build/dist/TikTok Transcriber`; the verified
ZIP and installer go to `dev/dist`. It does not overwrite an installed copy.

macOS and Linux:

```bash
bash dev/build.sh            # add --strict to fail when a packaging tool is missing
```

Linux packaging uses `appimagetool` and `nfpm` from PATH; the release workflow
installs pinned, checksum-verified versions. See [media libraries](MEDIA.md) for
how each system's FFmpeg libraries are sourced.

## Release workflow

`.github/workflows/release.yml` builds every package on its own system and starts
each built app for 40 seconds as a smoke test (no model download). A `v*` tag
whose version matches `APP_VERSION` publishes the release with all packages,
`SHA256SUMS.txt` and `package-manifests.zip`, but only after every build, the
portable ZIP check and every distribution container have passed.

## Package managers

`dev/update_manifests.py <version> SHA256SUMS.txt` writes the manifests; the
release workflow runs it and attaches the result as `package-manifests.zip`.

| Channel | File | After publishing |
|---|---|---|
| Homebrew | `Casks/tiktok-transcriber.rb` | Commit it: this repository is its own tap. |
| Scoop | `bucket/tiktok-transcriber.json` | Commit it: this repository is its own bucket. |
| winget | `packaging/winget/<version>/` | Submit to microsoft/winget-pkgs (`wingetcreate submit`). |
| AUR | `packaging/aur/PKGBUILD`, `.SRCINFO` | Push to the `tiktok-transcriber-bin` AUR repository. |
| PyPI | wheel and source archive | `twine upload` or trusted publishing from the PyPI project. |
| Flathub | `packaging/linux/flatpak/` | Optional: a Flathub submission must build from sources. |

## Maintainer checklist

1. Update `APP_VERSION`, `dev/version_info.txt`, the AppStream release list, the
   README download links and the changelog together.
2. Pass the offline and interactive checks in [VALIDATION.md](VALIDATION.md).
3. Build with the pinned [media inputs](MEDIA.md), then run
   `dev/model_binary_check.py` against the exact Windows release executable.
4. Exercise real speech, no speech, CPU, GPU fallback, and export paths in the
   built apps. Check that ordinary startup does not download weights.
5. Inspect package contents, licenses, dependency inventory, and checksums.
6. Keep the pinned upstream FFmpeg input archive and source materials available
   with the release, as documented in MEDIA.md.
7. Tag the reviewed source commit; the workflow publishes the release when every
   check passes. Then commit the generated Homebrew and Scoop manifests and submit
   the others.

The initial source tag is `v0.1.0`. Model downloads remain at their pinned upstream
repositories and are not included in any package.
