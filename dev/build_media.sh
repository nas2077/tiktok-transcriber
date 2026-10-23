#!/usr/bin/env bash
# LGPL-only FFmpeg for macOS and Linux, and PyAV 18.1.0 compiled against it.
#
# The PyAV wheels on PyPI for these systems bundle FFmpeg with x264 and x265,
# which are GPL. The Windows build avoids them with BtbN's LGPL libraries
# (dev/prepare_media.py); here the same pinned FFmpeg revision is compiled
# from source without any external codec library. See docs/MEDIA.md.
#
#   bash dev/build_media.sh dev/.venv/bin/python
set -euo pipefail

DEV="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$1"
MEDIA="$DEV/media/unix"
PREFIX="$MEDIA/ffmpeg"
REVISION=46d899d7a02bc63237472cc4897258d5ddf274ac
SHA256=6626e1f622324597146a8cc90a89bb4c3529f7df55f0a8c998fde55ac5ae4161
SOURCES=(
    "https://codeload.github.com/FFmpeg/FFmpeg/tar.gz/$REVISION"
    "https://github.com/nas2077/tiktok-transcriber/releases/download/v0.1.0/FFmpeg-46d899d7a02b-source.tar.gz"
)

sha256() {
    if command -v sha256sum >/dev/null; then sha256sum "$1" | cut -d' ' -f1
    else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

if [ ! -f "$PREFIX/lib/pkgconfig/libavcodec.pc" ]; then
    mkdir -p "$MEDIA"
    archive="$MEDIA/FFmpeg-${REVISION:0:12}-source.tar.gz"
    if [ ! -f "$archive" ] || [ "$(sha256 "$archive")" != "$SHA256" ]; then
        for url in "${SOURCES[@]}"; do
            curl -fsSL --retry 3 -o "$archive.partial" "$url" || continue
            if [ "$(sha256 "$archive.partial")" = "$SHA256" ]; then
                mv "$archive.partial" "$archive"
                break
            fi
            echo "SHA-256 mismatch: $url" >&2
        done
    fi
    [ -f "$archive" ] || { echo "Could not download the pinned FFmpeg source" >&2; exit 1; }
    rm -rf "$MEDIA/src"
    mkdir -p "$MEDIA/src"
    tar -xzf "$archive" -C "$MEDIA/src" --strip-components 1
    options=(
        --prefix="$PREFIX" --enable-shared --disable-static --enable-version3
        --disable-programs --disable-doc --disable-debug
        # no auto-detected outside libraries: nothing GPL can slip in
        --disable-autodetect --enable-pthreads --enable-zlib
    )
    case "$(uname -m)" in
        x86_64|amd64) options+=(--disable-x86asm) ;;  # no nasm needed; audio decoding is light
    esac
    if [ "$(uname -s)" = Darwin ]; then
        options+=(--install-name-dir="$PREFIX/lib")
    fi
    (cd "$MEDIA/src" && ./configure "${options[@]}" && make -j"$(getconf _NPROCESSORS_ONLN)" && make install)
fi

export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig"
if [ "$(uname -s)" = Linux ]; then
    export LD_LIBRARY_PATH="$PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
"$PY" -m pip install --disable-pip-version-check -q --force-reinstall --no-deps \
    --no-binary av --no-cache-dir "av==18.1.0"
"$PY" - <<'EOF'
import av._core as core
for name, meta in core.library_meta.items():
    configuration = meta["configuration"]
    assert "GPL" not in meta["license"].replace("LGPL", ""), (name, meta["license"])
    for forbidden in ("--enable-gpl", "--enable-nonfree", "libx264", "libx265"):
        assert forbidden not in configuration, (name, forbidden)
print("PyAV", core.library_versions["libavcodec"], "linked to LGPL-only FFmpeg:",
      core.library_meta["libavcodec"]["license"])
EOF
