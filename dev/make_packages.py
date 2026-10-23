"""Turn the PyInstaller build into the macOS and Linux release packages.

macOS: Syllark-<version>-macos-<arm64|x64>.dmg
Linux: Syllark-<version>-linux-<arch>.tar.gz and .AppImage, plus .deb, .rpm and
       an Arch package through nfpm.

Run by dev/build.sh after PyInstaller. `appimagetool` and `nfpm` must be on
PATH for the Linux formats that need them; a missing tool is reported and
that format is skipped unless --strict is given (the release workflow uses
--strict). Windows packages come from dev/build.ps1.
"""
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEV = ROOT / "dev"
BUILD = DEV / "build" / "dist"
DIST = DEV / "dist"
LINUX_FILES = ROOT / "packaging" / "linux"
APP_ID = "io.github.nas2077.Syllark"


def version():
    text = (ROOT / "src" / "tiktok_core.py").read_text(encoding="utf-8")
    return re.search(r'^APP_VERSION = "([^"]+)"', text, re.M)[1]


def machine():
    name = platform.machine().lower()
    return {"amd64": "x86_64", "arm64": "aarch64"}.get(name, name)


def run(*command, **options):
    print("+", " ".join(str(c) for c in command), flush=True)
    subprocess.run([str(c) for c in command], check=True, **options)


def missing(tool, strict):
    if shutil.which(tool):
        return False
    if strict:
        raise SystemExit(f"{tool} is required")
    print(f"skipped: {tool} is not installed", flush=True)
    return True


# ------------------------------------------------------------------ macOS


def mac(ver):
    app = BUILD / "Syllark.app"
    if not (app / "Contents" / "MacOS" / "Syllark").is_file():
        raise SystemExit("Expected dev/build/dist/Syllark.app")
    arch = "arm64" if machine() == "aarch64" else "x64"
    target = DIST / f"Syllark-{ver}-macos-{arch}.dmg"
    with tempfile.TemporaryDirectory() as folder:
        stage = Path(folder) / "Syllark"
        stage.mkdir()
        # symlinks=True keeps the frameworks' internal links, which the
        # signature of the bundle depends on
        shutil.copytree(app, stage / "Syllark.app", symlinks=True)
        (stage / "Applications").symlink_to("/Applications")
        target.unlink(missing_ok=True)
        run("hdiutil", "create", "-volname", "Syllark", "-srcfolder", stage,
            "-fs", "HFS+", "-format", "UDZO", "-imagekey", "zlib-level=9", "-ov", target)
    run("hdiutil", "verify", target)
    return [target]


# ------------------------------------------------------------------ Linux


def linux(ver, strict):
    bundle = BUILD / "Syllark"
    if not (bundle / "Syllark").is_file():
        raise SystemExit("Expected dev/build/dist/Syllark/Syllark")
    arch = machine()
    made = [tarball(bundle, ver, arch)]
    if not missing("appimagetool", strict):
        made.append(appimage(bundle, ver, arch))
    if not missing("nfpm", strict):
        made += native_packages(ver, arch)
    return made


def tarball(bundle, ver, arch):
    """the bundle plus its desktop entry, for anyone who installs by hand"""
    target = DIST / f"Syllark-{ver}-linux-{arch}.tar.gz"
    with tarfile.open(target, "w:gz", compresslevel=9) as archive:
        archive.add(bundle, "Syllark")
        archive.add(LINUX_FILES / f"{APP_ID}.desktop", f"Syllark/{APP_ID}.desktop")
        archive.add(LINUX_FILES / f"{APP_ID}.metainfo.xml", f"Syllark/{APP_ID}.metainfo.xml")
        archive.add(ROOT / "src" / "icon.png", f"Syllark/{APP_ID}.png")
    with tarfile.open(target) as archive:
        names = archive.getnames()
        assert "Syllark/Syllark" in names and f"Syllark/{APP_ID}.desktop" in names
    return target


def appimage(bundle, ver, arch):
    """one file that runs on any recent distribution"""
    target = DIST / f"Syllark-{ver}-linux-{arch}.AppImage"
    with tempfile.TemporaryDirectory() as folder:
        appdir = Path(folder) / "Syllark.AppDir"
        shutil.copytree(bundle, appdir / "usr" / "lib" / "syllark", symlinks=True)
        shutil.copy2(LINUX_FILES / f"{APP_ID}.desktop", appdir / f"{APP_ID}.desktop")
        shutil.copy2(ROOT / "src" / "icon.png", appdir / f"{APP_ID}.png")
        icons = appdir / "usr" / "share" / "icons" / "hicolor" / "512x512" / "apps"
        icons.mkdir(parents=True)
        shutil.copy2(ROOT / "src" / "icon.png", icons / f"{APP_ID}.png")
        metainfo = appdir / "usr" / "share" / "metainfo"
        metainfo.mkdir(parents=True)
        shutil.copy2(LINUX_FILES / f"{APP_ID}.metainfo.xml", metainfo / f"{APP_ID}.appdata.xml")
        apprun = appdir / "AppRun"
        apprun.write_text('#!/bin/sh\nHERE="$(dirname "$(readlink -f "$0")")"\n'
                          'exec "$HERE/usr/lib/syllark/Syllark" "$@"\n', encoding="utf-8")
        apprun.chmod(0o755)
        target.unlink(missing_ok=True)
        env = dict(os.environ, ARCH=arch, APPIMAGE_EXTRACT_AND_RUN="1")
        run("appimagetool", "--no-appstream", appdir, target, env=env)
    target.chmod(0o755)
    return target


def native_packages(ver, arch):
    """.deb, .rpm and the Arch package, all from packaging/linux/nfpm.yaml"""
    goarch = {"x86_64": "amd64", "aarch64": "arm64"}.get(arch, arch)
    env = dict(os.environ, SYLLARK_VERSION=ver, SYLLARK_ARCH=goarch)
    made = []
    for packager in ("deb", "rpm", "archlinux"):
        before = set(DIST.iterdir())
        run("nfpm", "package", "--config", LINUX_FILES / "nfpm.yaml",
            "--packager", packager, "--target", DIST, cwd=ROOT, env=env)
        made += sorted(set(DIST.iterdir()) - before)
    return made


def main():
    strict = "--strict" in sys.argv[1:]
    DIST.mkdir(parents=True, exist_ok=True)
    ver = version()
    if sys.platform == "darwin":
        made = mac(ver)
    elif sys.platform.startswith("linux"):
        made = linux(ver, strict)
    else:
        raise SystemExit("Windows packages come from dev/build.ps1")
    for path in made:
        print(f"OK: {path.name} · {path.stat().st_size / 1048576:.1f} MB", flush=True)


if __name__ == "__main__":
    main()
