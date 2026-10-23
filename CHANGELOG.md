# Changelog

## 0.2.0 — unreleased

Syllark on macOS and Linux, and more ways to install it.

- macOS 11+ on Apple silicon and Intel: disk images and a Homebrew cask. Natural
  can use Metal on Apple silicon.
- Linux x86_64 and aarch64: AppImage, `.deb`, `.rpm`, Arch package, `.tar.gz`, and
  a Flatpak for x86_64. Whisper can use already installed NVIDIA libraries or
  download them, as on Windows.
- Windows: a per-user installer with Start menu entry and uninstaller, next to the
  portable ZIP; Scoop and winget manifests.
- One-line terminal installs (`install.sh`, `install.ps1`) that verify SHA-256
  before installing, and a Python package (`pipx install syllark`).
- macOS and Linux keep the system title bar; Windows keeps Syllark's own.
- All packages keep LGPL-only FFmpeg libraries without x264/x265. The Linux window
  uses the LGPL PySide6.
- Release workflow: every package is built on its own system and started as a
  smoke test; a version tag drafts the release with checksums and manifests.
- certifi 2026.10.19 fixes PYSEC-2026-4320.

## 0.1.0 — 2026-10-15

First public Syllark release.

- Local Qwen and Whisper recognition behind four integrated model choices.
- Public TikTok video/profile processing, a selectable gallery, photo-post audio,
  resume, per-video exports, combined collections, and a metadata index.
- Markdown/plain text, optional timestamps, and readable paragraph boundaries.
- Nas interface with a distinct Syllark bird mark, 14 languages, light/dark themes,
  keyboard controls, and reduced motion.
- English source documentation, automated regression/security checks, dependency
  inventory, third-party license texts, and LGPL-only shared media libraries.

- Parsed TikTok host validation rejects misleading domains and off-site share
  redirects before making a public request.

Existing local settings keep their legacy storage location for compatibility.
See [validation](docs/VALIDATION.md) for measured coverage and known limitations.
