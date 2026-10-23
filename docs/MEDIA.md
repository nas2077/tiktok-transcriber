# Media libraries

The application reads audio through PyAV. PyPI's PyAV wheels include FFmpeg
libraries with additional codec-license considerations: the macOS and Linux
wheels, for example, are configured with x264 and x265, which are GPL. Every
TikTok Transcriber package therefore uses LGPL-only FFmpeg libraries without x264/x265.

## macOS and Linux

`dev/build_media.sh` (run by `dev/build.sh`) downloads the same pinned FFmpeg
revision used for Windows, `46d899d7a02bc63237472cc4897258d5ddf274ac`, verifies
its SHA-256 (the archive listed in [media-sources.json](media-sources.json)), and
compiles it with `--enable-version3 --disable-autodetect`, threads and zlib, and
no external codec library. PyAV 18.1.0 is then compiled from its PyPI source
against those libraries. The script refuses a result whose configuration
contains `--enable-gpl`, `--enable-nonfree`, x264 or x265. FFmpeg's own decoders
cover the AAC, MP3, Opus, Vorbis and FLAC audio TikTok Transcriber reads.

The Linux window uses Qt through PySide6, which is LGPL; PyQt is not bundled.

## Windows

## Inputs and modification

`dev/media.lock.json` records the original PyAV 18.1.0 wheel and the FFmpeg
archive URLs and SHA-256 values. The upstream BtbN archive is mirrored as a
release asset because its daily archives have a limited retention period.

```powershell
dev\.venv\Scripts\python.exe dev\prepare_media.py
dev\.venv\Scripts\python.exe -m pip install --no-deps --force-reinstall dev\media\av-18.1.0+lgpl.1-cp311-abi3-win_amd64.whl
```

The script verifies both archives, checks every imported FFmpeg symbol, changes
40 extension import tables to the standard shared-library names, replaces the
bundled libraries, and rebuilds wheel metadata/RECORD. It changes no extension
instructions or application recognition logic. The wheel carries an explicit
local version and modification notice.

The DLLs remain separate in the application runtime. Replacement libraries must
provide the imported FFmpeg ABI; the repacking script checks symbol availability.
Build outputs and input archives stay under ignored `dev/media`.

## Sources and build materials

- [FFmpeg source at the distributed revision](https://github.com/FFmpeg/FFmpeg/tree/46d899d7a0).
- [BtbN build scripts and dependency source definitions](https://github.com/BtbN/FFmpeg-Builds/tree/63ac3265b0789ea16c7b1f8351cd2ad195a28722).
- [PyAV 18.1.0 source](https://github.com/PyAV-Org/PyAV/tree/v18.1.0).
- TikTok Transcriber's import-table changes and packaging instructions: `dev/prepare_media.py`.

The BtbN tree contains the component source URLs, patches, configuration, and
container build steps. Its relevant target is `win64`, variant `lgpl-shared`,
release branch `8.1`; the FFmpeg commit is fixed by the lock file. The release also retains source snapshots for FFmpeg, PyAV, and the BtbN build
scripts; their revisions, original download URLs, and checksums are in
[media-sources.json](media-sources.json). Preserve these materials and source
access with a release. Read the full LGPL/GPL terms in
`src/licenses` rather than treating a metadata label as a certification.

## Verification

The resulting runtime reports LGPL version 3 or later and has no x264/x265 DLLs
or enabled GPL configuration. 124 retained WAV recordings decode to exactly the
same samples as the previous package. Frozen CPU/Vulkan inference and live
download/export checks are recorded separately in the release validation notes.
