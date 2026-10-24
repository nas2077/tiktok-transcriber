# Changelog

## 0.2.2 — 2026-10-24

Security update.

- filelock 4.2.1 fixes six advisories published on 2026-10-23 (CVE-2026-112906,
  CVE-2026-112907, CVE-2026-112913, CVE-2026-112914, CVE-2026-112937,
  CVE-2026-112940). In each, another user on the same computer could abuse the
  lock files that model downloads use, to overwrite or delete the files of the
  person running the app, or to hold a lock past its timeout. Every 0.2.1
  package carried filelock 4.1.1; please update.
- Windows: the portable ZIP opens. Explorer marks every file taken out of
  a downloaded ZIP as coming from the internet, and the .NET Framework refused
  the marked window libraries: 0.2.0 and 0.2.1 stopped with "the app could not
  start". The app now clears the mark from its own runtime folder. The
  installer was never affected. The release build now starts the extracted,
  marked ZIP too.
- Windows: without the Microsoft Edge WebView2 Runtime the app says so and
  opens its download page, instead of showing a window that does not work.
- Closing the window during a job ends the app at once. A copy still winding
  down kept the one-window lock, and the next start did nothing; a second
  start also no longer brings an Explorer folder named "TikTok Transcriber"
  forward instead of the app.
- Linux: the sleep inhibitor no longer outlives the app (the computer could
  stay awake until restarted) or leaves a process behind after every job.
- Links without "www", from m.tiktok.com, and photo posts open as that one
  post; a photo link used to start its whole profile, and gallery photo posts
  could fail with "unsupported URL".
- Stop and the gallery's Cancel interrupt a Whisper transcription between
  segments instead of waiting for the whole video.
- Switching from Natural to Whisper in the gallery runs as many transcriptions
  in parallel as Whisper can, not one.

## 0.2.1 — 2026-10-23

Security update.

- Brotli 1.2.1 fixes CVE-2026-111497 (PYSEC-2026-4322), an out-of-bounds write in
  the Brotli decoder that a crafted compressed network response could reach.
  Every 0.2.0 package carried Brotli 1.2.0; please update.

## 0.2.0 — 2026-10-23

Syllark is now **TikTok Transcriber**, on macOS and Linux too, with more ways to
install it. The repository moved to `nas2077/tiktok-transcriber`; old links redirect.

- A new icon from the Nas periodic table of projects: element 01, `Tt`, an app.
- macOS 11+ on Apple silicon and Intel: disk images and a Homebrew cask. Natural
  can use Metal on Apple silicon.
- Linux x86_64 and aarch64: AppImage, `.deb`, `.rpm`, Arch package, `.tar.gz`, and
  a Flatpak for x86_64. Whisper can use already installed NVIDIA libraries or
  download them, as on Windows.
- Windows: a per-user installer with Start menu entry and uninstaller, next to the
  portable ZIP; Scoop and winget manifests.
- One-line terminal installs (`install.sh`, `install.ps1`) that verify SHA-256
  before installing, and a Python wheel for `pipx install` from the release.
- The Linux packages use the system's C++ runtime and the libraries its OpenGL
  driver needs: on Ubuntu 24.04, Debian 13, Fedora 42, Arch and openSUSE the
  window aborted with "Could not initialize GLX" before. Docks pair the window
  with its menu entry and icon.
- macOS and Linux keep the system title bar; Windows keeps the app's own.
- All packages keep LGPL-only FFmpeg libraries without x264/x265. The Linux window
  uses the LGPL PySide6.
- Release workflow: every package is built on its own system and started as a
  smoke test; a version tag drafts the release with checksums and manifests.
- Gallery: a profile explored right after stopping another no longer receives
  the previous profile's last videos. Saved choices show in every picker at
  startup. Video links stay the TikTok page, never a signed file address.
- Windows: a pinned taskbar shortcut and the running window share one button.
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
