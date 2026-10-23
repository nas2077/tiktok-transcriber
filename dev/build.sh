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
"$PY" -m pip install --disable-pip-version-check -q -r "$DEV/requirements.txt" \
    -c "$DEV/constraints.txt" -r "$DEV/requirements-dev.txt"
"$PY" "$DEV/collect_licenses.py"
"$PY" -m PyInstaller --noconfirm --clean --log-level WARN \
    --distpath "$DEV/build/dist" --workpath "$DEV/build/work" "$DEV/build.spec"
"$PY" "$DEV/make_packages.py" "$@"
