<p align="center"><img src=".github/assets/icon.svg" width="128" height="128" alt="TikTok Transcriber"></p>

<h1 align="center">TikTok Transcriber.</h1>
<p align="center">Public clips. Clear text. On your computer.</p>

[![Checks](https://github.com/nas2077/tiktok-transcriber/actions/workflows/checks.yml/badge.svg)](https://github.com/nas2077/tiktok-transcriber/actions/workflows/checks.yml) [![CodeQL](https://github.com/nas2077/tiktok-transcriber/actions/workflows/codeql.yml/badge.svg)](https://github.com/nas2077/tiktok-transcriber/actions/workflows/codeql.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-a35139.svg)](LICENSE)

TikTok Transcriber turns public TikTok videos and profiles into readable transcripts on Windows, macOS, and Linux. Recognition runs locally with integrated Qwen and Whisper models. Paste a link, choose an output folder, and start.

## Features

- Transcribe one video, selected gallery items, or a complete public profile.
- Readable paragraphs in Markdown or plain text, with optional timestamps.
- A per-video file, combined collection, and CSV metadata index.
- Resume previous work and retry individual videos.
- Preview covers and save original videos as MP4.
- Four integrated model choices with automatic downloads.
- Fourteen interface languages, dark/light themes, and reduced motion.

<picture>
  <source media="(prefers-color-scheme: light)" srcset=".github/assets/screenshot-light.png">
  <img src=".github/assets/screenshot-dark.png" alt="TikTok Transcriber on Windows" width="1120">
</picture>

## Download

| System | Packages |
|---|---|
| **Windows** 10/11 · x64 | [Installer](https://github.com/nas2077/tiktok-transcriber/releases/download/v0.2.0/TikTok-Transcriber-0.2.0-windows-x64-setup.exe) · [Portable ZIP](https://github.com/nas2077/tiktok-transcriber/releases/download/v0.2.0/TikTok-Transcriber-0.2.0-windows-x64.zip) |
| **macOS** 11+ | [Apple silicon](https://github.com/nas2077/tiktok-transcriber/releases/download/v0.2.0/TikTok-Transcriber-0.2.0-macos-arm64.dmg) · [Intel](https://github.com/nas2077/tiktok-transcriber/releases/download/v0.2.0/TikTok-Transcriber-0.2.0-macos-x64.dmg) |
| **Linux** · x86_64 | [AppImage](https://github.com/nas2077/tiktok-transcriber/releases/download/v0.2.0/TikTok-Transcriber-0.2.0-linux-x86_64.AppImage) · [.deb](https://github.com/nas2077/tiktok-transcriber/releases/download/v0.2.0/tiktok-transcriber_0.2.0-1_amd64.deb) · [.rpm](https://github.com/nas2077/tiktok-transcriber/releases/download/v0.2.0/tiktok-transcriber-0.2.0-1.x86_64.rpm) · [Arch](https://github.com/nas2077/tiktok-transcriber/releases/download/v0.2.0/tiktok-transcriber-0.2.0-1-x86_64.pkg.tar.zst) · [Flatpak](https://github.com/nas2077/tiktok-transcriber/releases/download/v0.2.0/TikTok-Transcriber-0.2.0-linux-x86_64.flatpak) · [.tar.gz](https://github.com/nas2077/tiktok-transcriber/releases/download/v0.2.0/TikTok-Transcriber-0.2.0-linux-x86_64.tar.gz) |
| **Linux** · ARM64 | [AppImage](https://github.com/nas2077/tiktok-transcriber/releases/download/v0.2.0/TikTok-Transcriber-0.2.0-linux-aarch64.AppImage) · [.deb](https://github.com/nas2077/tiktok-transcriber/releases/download/v0.2.0/tiktok-transcriber_0.2.0-1_arm64.deb) · [.rpm](https://github.com/nas2077/tiktok-transcriber/releases/download/v0.2.0/tiktok-transcriber-0.2.0-1.aarch64.rpm) · [Arch](https://github.com/nas2077/tiktok-transcriber/releases/download/v0.2.0/tiktok-transcriber-0.2.0-1-aarch64.pkg.tar.zst) · [.tar.gz](https://github.com/nas2077/tiktok-transcriber/releases/download/v0.2.0/TikTok-Transcriber-0.2.0-linux-aarch64.tar.gz) |

Every package carries its own Python and speech engines. [Releases](https://github.com/nas2077/tiktok-transcriber/releases) list checksums and release notes.

### Install from a terminal

macOS and Linux, no root needed:

```bash
curl -fsSL https://raw.githubusercontent.com/nas2077/tiktok-transcriber/main/install.sh | sh
```

Windows, in PowerShell, no administrator rights needed:

```powershell
irm https://raw.githubusercontent.com/nas2077/tiktok-transcriber/main/install.ps1 | iex
```

Both scripts download the latest release and check its SHA-256 before installing.

<details>
<summary><b>Package managers and distributions</b></summary>

```bash
# macOS · Homebrew
brew tap nas2077/tiktok-transcriber https://github.com/nas2077/tiktok-transcriber
brew install --cask tiktok-transcriber
```

```powershell
# Windows · winget
winget install nas2077.TikTokTranscriber   # once Microsoft accepts the submission
# Windows · Scoop
scoop bucket add tiktok-transcriber https://github.com/nas2077/tiktok-transcriber
scoop install tiktok-transcriber
```

```bash
# Debian, Ubuntu, Linux Mint, Pop!_OS, elementary OS, Zorin OS, Kali
sudo apt install ./tiktok-transcriber_0.2.0-1_amd64.deb
# Fedora, and RHEL, Rocky Linux or AlmaLinux 10
sudo dnf install ./tiktok-transcriber-0.2.0-1.x86_64.rpm
# openSUSE
sudo zypper install ./tiktok-transcriber-0.2.0-1.x86_64.rpm
# Arch Linux, Manjaro, EndeavourOS
sudo pacman -U ./tiktok-transcriber-0.2.0-1-x86_64.pkg.tar.zst
# Any distribution · Flatpak (with Flathub set up for its runtime)
flatpak install --user ./TikTok-Transcriber-0.2.0-linux-x86_64.flatpak
# Any distribution · AppImage
chmod +x TikTok-Transcriber-0.2.0-linux-x86_64.AppImage && ./TikTok-Transcriber-0.2.0-linux-x86_64.AppImage
```

```bash
# Any system with Python 3.11 or newer
pipx install https://github.com/nas2077/tiktok-transcriber/releases/download/v0.2.0/tiktok_transcriber-0.2.0-py3-none-any.whl
```

</details>

Requirements: Windows 10/11 x64 with WebView2; macOS 11 or newer; Linux with X11 or Wayland and glibc 2.35+ (x86_64) or 2.39+ (ARM64), such as Ubuntu 22.04/24.04, Debian 12/13, Linux Mint 21/22, Fedora 36/40, openSUSE Tumbleweed, Arch, or RHEL/Rocky/Alma 10 and newer. The Flatpak also runs on older systems such as RHEL 9, and on immutable ones. Packages are not signed with a publisher certificate: Windows SmartScreen may warn, and macOS asks you to choose **Open Anyway** in System Settings › Privacy & Security the first time. See [release verification](docs/RELEASING.md) before running a downloaded build.

## Use

1. Paste `@someone`, a public profile/video URL, or a TikTok share link.
2. Choose the output folder and model in Options.
3. Press **Transcribe**, or use the Gallery for individual items.

The selected model downloads on first use. Natural needs about **2.3 GB** including language detection. Later jobs reuse the cache. No external model manager or transcription account is required. Opening the app alone does not download a model.

Previously transcribed videos are skipped by default. Turn off **Skip already transcribed** or redo an individual Gallery item to replace its saved transcript.

## Models

| Choice | Engine | Download |
|---|---|---:|
| Natural | Qwen3-ASR 1.7B Q8_0 | 2.3 GB |
| Balanced | Whisper large-v3-turbo | 1.6 GB |
| Thorough | Whisper large-v3 | 3.1 GB |
| Lightweight | Whisper small | 0.5 GB |

Natural is the default for new settings and includes CPU/Vulkan support. Whisper can download NVIDIA libraries when needed and also works on CPU. Recognition can make mistakes. **Natural timestamps mark audio block starts, not individual words.** [Model details and limits](docs/MODELS.md).

## Privacy

TikTok Transcriber uses public TikTok access without sign-in, browser-session reads, or imported account cookies. Audio is not uploaded to a transcription service. Network access is used for TikTok content, model/library downloads, and the interface font. [Full privacy and storage details](docs/PRIVACY.md).

## Development

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File dev\setup.ps1 -Quiet
dev\run.bat
```

```bash
# macOS and Linux
python3 -m venv dev/.venv
dev/.venv/bin/pip install -r dev/requirements.txt -c dev/constraints.txt
dev/.venv/bin/python src/app.py
```

Development uses Python 3.12 and `dev/.venv`. Packages are built with `dev\build.ps1` on Windows and `dev/build.sh` on macOS and Linux; see [releases](docs/RELEASING.md). See [contributing](CONTRIBUTING.md), [architecture](docs/ARCHITECTURE.md), and [validation](docs/VALIDATION.md).

## Repository and releases

This repository contains source, documentation, tests, and artwork. Environments, model caches, downloaded media, build intermediates, and executables are excluded. Packages for every system belong in Releases; model weights are downloaded from their upstream hosts. A small source checkout does not mean the installed models are small.

Project documentation and code use English. The app remains localized in 14 languages; translation values and multilingual fixtures retain their own languages.

## License

Original code and artwork: [MIT](LICENSE). Bundled and downloaded components have their own licenses; see [third-party notices](THIRD_PARTY_NOTICES.md) and `src/licenses`. Use content you have permission to download and transcribe.

<p align="center"><a href="https://github.com/nas2077"><img src=".github/assets/signature.svg" width="52" height="36" alt="Nas"></a><br>Made by Nas.</p>
