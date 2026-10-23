# PyInstaller folder build. Run through dev/build.ps1 (Windows) or dev/build.sh
# (macOS, Linux). Shared runtime libraries remain separate; optional CUDA
# libraries download on demand.
import os
import re
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

ROOT = os.path.dirname(SPECPATH)
SRC = os.path.join(ROOT, "src")
WINDOWS = sys.platform == "win32"
MAC = sys.platform == "darwin"
LINUX = not WINDOWS and not MAC
# read, not imported: importing tiktok_core would set up the whole engine
with open(os.path.join(SRC, "tiktok_core.py"), encoding="utf-8") as f:
    APP_VERSION = re.search(r'^APP_VERSION = "([^"]+)"', f.read(), re.M)[1]

datas = [
    (os.path.join(ROOT, "LICENSE"), "licenses"),
    (os.path.join(ROOT, "THIRD_PARTY_NOTICES.md"), "licenses"),
    (os.path.join(SRC, "i18n.js"), "."),
    (os.path.join(SRC, "controls.js"), "."),
    (os.path.join(SRC, "locales"), "locales"),
    (os.path.join(SRC, "licenses"), "licenses"),
    (os.path.join(SRC, "ui.html"), "."),
    (os.path.join(SRC, "icon.ico"), "."),
    (os.path.join(SRC, "icon.png"), "."),
    (os.path.join(SRC, "vendor", "orbi.js"), "vendor"),
    (os.path.join(SRC, "vendor", "orbi-icons.js"), "vendor"),
    (os.path.join(SRC, "vendor", "nas.css"), "vendor"),
    (os.path.join(SRC, "vendor", "nas.js"), "vendor"),
]
binaries = []
hiddenimports = collect_submodules("yt_dlp.extractor")

# Include package data, native backends, and provider entry-point metadata.
packages = ["faster_whisper", "ctranslate2", "onnxruntime", "tokenizers", "av",
            "webview", "curl_cffi", "yt_dlp", "yt_dlp_ejs",
            "huggingface_hub", "certifi", "transcribe_cpp", "transcribe_cpp_native"]
if WINDOWS:
    packages += ["clr_loader", "pythonnet"]
for package in packages:
    try:
        d, b, h = collect_all(package)
    except Exception:
        continue
    datas += d
    binaries += b
    hiddenimports += h

# The window backend pywebview loads by name at runtime.
if MAC:
    hiddenimports += ["webview.platforms.cocoa", "AppKit", "Foundation", "WebKit",
                      "Quartz", "UniformTypeIdentifiers", "objc"]
elif LINUX:
    hiddenimports += ["webview.platforms.qt", "qtpy", "PyQt6.QtCore", "PyQt6.QtGui",
                      "PyQt6.QtWidgets", "PyQt6.QtNetwork", "PyQt6.QtWebChannel",
                      "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets"]

# The native provider is discovered through its Python package entry point.
for package in ("transcribe-cpp", "transcribe-cpp-native"):
    datas += copy_metadata(package)

# Other systems' window backends would only drag in libraries that are not there.
excludes = ["nvidia", "tkinter", "matplotlib", "torch", "tensorflow", "IPython", "pytest"]
if not LINUX:
    excludes += ["PyQt5", "PyQt6", "PySide2", "PySide6", "qtpy", "webview.platforms.qt",
                 "webview.platforms.gtk", "gi"]
else:
    excludes += ["PyQt5", "PySide2", "PySide6", "webview.platforms.gtk", "gi"]

a = Analysis(
    [os.path.join(SRC, "app.py")],
    pathex=[SRC],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

icon = (os.path.join(SRC, "icon.ico") if WINDOWS
        else os.path.join(SRC, "icon.png") if MAC else None)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Syllark",
    icon=icon,
    console=False,              # a window, no black console behind it
    contents_directory="runtime" if WINDOWS else "_internal",
    version=os.path.join(SPECPATH, "version_info.txt") if WINDOWS else None,
    upx=False,                  # compressed dlls trip antiviruses and start slower
)

coll = COLLECT(exe, a.binaries, a.datas, name="Syllark", upx=False)

if MAC:
    app = BUNDLE(
        coll,
        name="Syllark.app",
        icon=icon,
        bundle_identifier="io.github.nas2077.syllark",
        version=APP_VERSION,
        info_plist={
            "CFBundleName": "Syllark",
            "CFBundleDisplayName": "Syllark",
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundleVersion": APP_VERSION,
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
            "LSApplicationCategoryType": "public.app-category.productivity",
        },
    )
