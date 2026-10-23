# Validation

Recorded on Windows 11 x64 with WebView2, Python 3.12, and an RTX 4060.
Results describe observed coverage; they do not guarantee transcription accuracy.

## Automated regressions

Run from the repository root after `dev/setup.ps1`:

```powershell
dev\.venv\Scripts\python.exe dev\repository_check.py
dev\.venv\Scripts\python.exe dev\core_check.py
dev\.venv\Scripts\python.exe dev\access_check.py
dev\.venv\Scripts\python.exe dev\readability_check.py
dev\.venv\Scripts\python.exe dev\natural_contract_check.py
dev\.venv\Scripts\python.exe dev\model_matrix_check.py
```

The release preparation passed 55 core, 24 anonymous-access, 72 readability,
and 10 native-contract checks. The matrix covered 10,080 export roundtrips,
4,320 pipelines with **mocked recognition/media**, and 41 engine/cache contracts.
These checks exercise application behavior, not speech-recognition quality.
GitHub Actions repeats this offline group and audits the pinned Python packages.

Interactive WebView2 checks passed 77 UI assertions, four models across all 14
locales and both themes, 144 focus checks, 240 navigation switches, localization,
anonymous-access controls, motion preferences, and command handling. These
require an interactive Windows desktop and run locally rather than on CI: on
GitHub's Windows runner the page never animates, and the same checks fail there
for the 0.1.0 source too.

## macOS and Linux (0.2.0 packaging)

GitHub Actions runs the offline group on Windows, Ubuntu 24.04 and macOS 15.
The release workflow builds every package on its own system: Windows x64,
macOS arm64 and x64, Linux x86_64 (Ubuntu 22.04) and aarch64 (Ubuntu 24.04). It
starts each built app for 40 seconds with a disposable profile and requires it to
stay open without a crash log; on Linux it runs under Xvfb. It also checks that
the bundled Qt, its platform plugins and the media libraries resolve, that PyAV
reports LGPL-only FFmpeg without x264/x265, and that the Python wheel installs
and runs `tiktok-transcriber --version`.

The release workflow also makes the operating system's voice say a sentence and
transcribes it with each built app (Whisper small everywhere, Natural on macOS
arm64 and Linux x86_64), installs and uninstalls the Windows installer and
`install.sh` on macOS and Linux, and installs each Linux package with the
distribution's own package manager in 14 clean containers: Ubuntu 22.04 and
24.04, Debian 12 and 13, Linux Mint 22, Fedora 42, AlmaLinux 10, openSUSE
Tumbleweed and Arch on x86_64, the AppImage on Fedora 42 and Debian 12, and
Ubuntu 24.04, Debian 13 and Fedora 42 on ARM64. Each must print its version and
keep its window open for 40 seconds on a 24-bit Xvfb screen with Mesa's
software OpenGL (AlmaLinux 10 has no Xvfb and uses Qt's offscreen platform).

Not yet verified on macOS or Linux: model downloads by hand, Metal and Vulkan
acceleration on real hardware, CUDA on Linux, the Flatpak on a desktop, Wayland
sessions, and the Homebrew, Scoop and winget installs on clean machines. The
offline check "an eta shows up" is timing-sensitive with mocked instant
recognition and failed once on macOS CI.

## Real audio and public network coverage

The recognition integration was exercised on 266 cases: 12 public creator clips
in automatic/manual Italian modes, 112 distinct FLEURS recordings in automatic
and manual modes across 14 languages, bilingual pairs, noisy recordings, and
noise/tone negatives. Additional checks covered digital silence, cancellation,
engine reuse, concurrent requests, and 96 creator export variants.

Anonymous network checks sampled 20 accessible public profiles and produced 39
transcripts. A separate complete NASA feed returned 56 posts: all 56 processed,
then all 56 skipped on resume without duplicates. Five unavailable discovery
attempts were recorded separately. A feed can change; these are observations
from the test date, not permanent account totals.

These broader integration runs preceded the TikTok Transcriber identity and media-packaging
changes. The recognition logic was retained. Release preparation repeated the
interactive regressions and tested the new executable with real offline CPU and
Vulkan inference on two speech recordings and a no-speech ASMR recording, with
four exports per case. The rebuilt media libraries decoded 124 retained WAVs to
bit-identical samples. The final binary check compares compiled application
modules, UI, vendor kit, catalogs, and license files against source, then opens
the executable with disposable settings and an empty model cache.

Creator listening samples came from public `@alexciriaco_` (12 clips, 589.49
seconds). They are not a complete account export or a human-verified gold corpus.
FLEURS samples are small diagnostics, not the official full benchmark. WER
normalization ignores punctuation; Chinese/Japanese diagnostics use CER.
Downloaded audio, transcripts, personal paths, model weights, and raw local
reports are excluded from the source repository.

## Security and limits

CodeQL and dependency auditing have separate workflow badges. The first CodeQL
run identified URL substring validation; it was replaced with parsed-host and
scheme validation, with regressions for spoofed domains, userinfo, unsafe ports,
and off-site redirects. The local Python
audit found no known vulnerabilities in the pinned dependency set at preparation
time. This does not audit every native DLL or prove absence of vulnerabilities.
Checksums verify package integrity; this release has no Windows code-signing
certificate and no third-party certification.

Not verified: a completely clean Windows installation, every GPU/driver,
spontaneous rapid code switching, overlapping speakers, or word alignment.
Natural timestamps identify audio-block starts. There is no ElevenLabs parity
claim, human-verified accuracy percentage, or promise of error-free recognition.

See [model limitations](MODELS.md), [media packaging](MEDIA.md), and
[release checks](RELEASING.md).
