#!/usr/bin/env bash
# Build Syllark on macOS or Linux: environment, licenses, PyInstaller, packages.
# Windows uses dev/build.ps1. Packages land in dev/dist; see docs/RELEASING.md.
set -euo pipefail

DEV="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
VENV="$DEV/.venv"

if [ ! -x "$VENV/bin/python" ]; then
    "$PYTHON" -m venv "$VENV"
fi
PY="$VENV/bin/python"
"$PY" -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11 or newer is required"'
CONSTRAINTS="$DEV/constraints.txt"
if [ "$(uname -s)-$(uname -m)" = "Darwin-x86_64" ]; then
    # onnxruntime 1.23.2 is the last release with Intel Mac wheels
    CONSTRAINTS="$DEV/build/constraints-macos-x64.txt"
    mkdir -p "$DEV/build"
    sed 's/^onnxruntime==.*/onnxruntime==1.23.2/' "$DEV/constraints.txt" > "$CONSTRAINTS"
fi
"$PY" -m pip install --disable-pip-version-check -q -r "$DEV/requirements.txt" \
    -c "$CONSTRAINTS" -r "$DEV/requirements-dev.txt"
# replace PyPI's PyAV (it bundles GPL x264/x265) with one on LGPL-only FFmpeg
bash "$DEV/build_media.sh" "$PY"
if [ "$(uname -s)" = Linux ]; then
    # PyInstaller finds the FFmpeg libraries the same way PyAV does
    export LD_LIBRARY_PATH="$DEV/media/unix/ffmpeg/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
"$PY" "$DEV/collect_licenses.py"
"$PY" -m PyInstaller --noconfirm --clean --log-level WARN \
    --distpath "$DEV/build/dist" --workpath "$DEV/build/work" "$DEV/build.spec"
"$PY" "$DEV/make_packages.py" "$@"
