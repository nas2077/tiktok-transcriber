"""Verify packaged sources and smoke-open this build with disposable settings."""
import argparse
import ctypes
import hashlib
import json
import marshal
import os
import subprocess
import tempfile
import time
import types
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader

from model_benchmark import ROOT, WORK, save


def signature(value):
    if isinstance(value, types.CodeType):
        return [value.co_code.hex(), signature(value.co_consts), value.co_names,
                value.co_varnames, value.co_freevars, value.co_cellvars, value.co_flags,
                value.co_argcount, value.co_posonlyargcount, value.co_kwonlyargcount]
    if isinstance(value, tuple):
        return [signature(x) for x in value]
    if isinstance(value, frozenset):
        return sorted(repr(x) for x in value)
    return value


def check(exe):
    archive = CArchiveReader(str(exe))
    pyz = archive.open_embedded_archive(next(k for k in archive.toc if k.endswith(".pyz")))
    assert "browser_access" not in pyz.toc
    report = {"exe": str(exe), "source_sha256": {}, "compiled_modules": [], "startup": False}
    assert "transcribe_cpp" in pyz.toc and "transcribe_cpp_native" in pyz.toc
    native = exe.parent / "runtime/transcribe_cpp_native/_native"
    assert (native / "transcribe.dll").is_file() and (native / "ggml-vulkan.dll").is_file()
    assert list(native.glob("ggml-cpu*.dll")), "CPU fallback backend is missing"
    assert not any((exe.parent / "runtime").rglob("*.gguf")), "Model weights were accidentally bundled"
    report["native_provider"] = "CPU/Vulkan, transcribe-cpp-native 0.4.0"
    for name in ("tiktok_core", "tiktok_public", "localization", "natural_asr", "runtime_check"):
        source = ROOT / "src" / (name + ".py")
        expected = compile(source.read_text(encoding="utf-8"), str(source), "exec")
        actual = pyz.extract(name)
        assert signature(expected) == signature(actual), "Packaged Python differs: " + name
        report["compiled_modules"].append(name)
        report["source_sha256"][source.name] = hashlib.sha256(source.read_bytes()).hexdigest()
    source = ROOT / "src/app.py"
    assert signature(compile(source.read_text(encoding="utf-8"), str(source), "exec")) == signature(marshal.loads(archive.extract("app")))
    report["compiled_modules"].append("app")
    report["source_sha256"][source.name] = hashlib.sha256(source.read_bytes()).hexdigest()
    for source in [ROOT / "src/ui.html", ROOT / "src/i18n.js", ROOT / "src/controls.js",
                   *(ROOT / "src/locales").glob("*.json"),
                   *(p for p in (ROOT / "src/licenses").rglob("*") if p.is_file()),
                   *(p for p in (ROOT / "src/vendor").rglob("*") if p.suffix in (".js", ".css"))]:
        relative = source.relative_to(ROOT / "src")
        bundled = exe.parent / "runtime" / relative
        assert source.read_bytes() == bundled.read_bytes(), "Packaged data differs: " + str(relative)
        report["source_sha256"][str(relative)] = hashlib.sha256(source.read_bytes()).hexdigest()
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        assert (ROOT / name).read_bytes() == (exe.parent / "runtime/licenses" / name).read_bytes()
    user32 = ctypes.windll.user32
    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
    enum_callback = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    with tempfile.TemporaryDirectory(prefix="model_binary_") as temporary:
        local = Path(temporary) / "TikTok Transcriber"
        local.mkdir()
        (local / "settings.json").write_text(json.dumps({"ui_language": "it", "theme": "dark", "motion": "off"}), encoding="utf-8")
        env = {**os.environ, "LOCALAPPDATA": temporary, "HF_HUB_CACHE": str(Path(temporary) / "models")}
        process = subprocess.Popen([str(exe)], cwd=str(exe.parent), env=env)
        hwnd = None
        try:
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline and process.poll() is None:
                windows = []

                @enum_callback
                def callback(window, _):
                    pid = ctypes.c_ulong()
                    user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
                    if pid.value == process.pid and user32.IsWindowVisible(window):
                        windows.append(window)
                    return True

                user32.EnumWindows(callback, 0)
                if windows:
                    hwnd = windows[0]
                    break
                time.sleep(.2)
            assert hwnd and process.poll() is None, "Executable did not open a window"
            time.sleep(5)
            assert process.poll() is None
            from screenshots import capture
            capture(hwnd, str(ROOT / "dev/shots/models-binary.png"))
            assert not (local / "crash.log").exists()
            assert not (local / "cuda").exists(), "Opening the app downloaded CUDA before a job"
            assert not any((Path(temporary) / "models").rglob("*.incomplete")), "Opening the app started model downloads"
            report["startup"] = True
            report["startup_downloads"] = False
            report["screenshot"] = "dev/shots/models-binary.png"
        finally:
            if hwnd:
                user32.PostMessageW(hwnd, 0x10, 0, 0)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
    report["passed"] = True
    save(WORK / "binary.json", report)
    print("PASS: compiled Python and all UI/catalog files match source; executable opened without a crash", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("exe", nargs="?", default=str(ROOT / "dev/build/tiktok-transcriber-dist/TikTok Transcriber/TikTok Transcriber.exe"))
    check(Path(parser.parse_args().exe).resolve())
