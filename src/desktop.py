"""Operating-system details: folders, opening files, sleep, theme, locale, one instance.

Windows keeps the exact calls it always used. macOS and Linux get their own
equivalents; anything that cannot be done on a system quietly does nothing,
because none of it is worth stopping a transcription for.
"""
import os
import subprocess
import sys
import threading

WINDOWS = sys.platform == "win32"
MAC = sys.platform == "darwin"
LINUX = not WINDOWS and not MAC
FROZEN = bool(getattr(sys, "frozen", False))


def system_name():
    return "windows" if WINDOWS else "macos" if MAC else "linux"


def prepare_window_engine():
    """
    before the window library loads. Qt WebEngine (the linux window) runs
    the page in a chromium sandbox that needs unprivileged user namespaces:
    a flatpak never has them, and ubuntu 24.04 blocks them for programs
    without an apparmor profile. there it would only crash on start, so it
    runs without that sandbox. the page is the app's own local html.
    """
    if not LINUX:
        return
    blocked = os.path.exists("/.flatpak-info")
    try:
        with open("/proc/sys/kernel/apparmor_restrict_unprivileged_userns") as f:
            blocked = blocked or f.read().strip() == "1"
    except OSError:
        pass
    try:
        with open("/proc/sys/kernel/unprivileged_userns_clone") as f:
            blocked = blocked or f.read().strip() == "0"
    except OSError:
        pass
    if blocked:
        os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")


# ------------------------------------------------------------------ folders


def data_base():
    """the folder every program keeps its own data in, on this system"""
    home = os.path.expanduser("~")
    if WINDOWS:
        return os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
    if MAC:
        return os.path.join(home, "Library", "Application Support")
    return os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")


def storage_name(windows_name):
    """
    windows keeps its old folder name, so nothing saved there is lost. the
    other systems start fresh and follow their own naming habits.
    """
    return windows_name if WINDOWS else "Syllark" if MAC else "syllark"


def documents_dir():
    """
    the real Documents folder.

    with onedrive backup turned on (the default on a fresh windows 11) it is
    not ~/Documents but ~/OneDrive/Documents, and writing into the first one
    creates a second, orphaned folder nobody ever looks at. linux desktops
    can rename it too (it is "Documenti" on an italian install).
    """
    home = os.path.expanduser("~")
    if WINDOWS:
        try:
            import ctypes

            buf = ctypes.create_unicode_buffer(260)
            # CSIDL_PERSONAL (5): the Documents folder, wherever the user moved it
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
                return buf.value
        except Exception:
            pass
    elif LINUX:
        folder = _xdg_documents(home)
        if folder:
            return folder
    return os.path.join(home, "Documents")


def _xdg_documents(home):
    config = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
    try:
        with open(os.path.join(config, "user-dirs.dirs"), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("XDG_DOCUMENTS_DIR="):
                    value = line.split("=", 1)[1].strip().strip('"')
                    value = value.replace("$HOME", home)
                    # pointing it at home itself means "no documents folder"
                    if value and os.path.normpath(value) != os.path.normpath(home):
                        return value
    except OSError:
        pass
    return None


# ------------------------------------------------------------------ opening things


def _clean_environment():
    """
    a bundled linux program changes LD_LIBRARY_PATH to find its own
    libraries. the file manager or browser it starts must not inherit that,
    or they load the bundle's copies and crash.
    """
    env = dict(os.environ)
    if LINUX and FROZEN:
        original = env.pop("LD_LIBRARY_PATH_ORIG", None)
        if original is None:
            env.pop("LD_LIBRARY_PATH", None)
        else:
            env["LD_LIBRARY_PATH"] = original
        env.pop("QT_PLUGIN_PATH", None)
        env.pop("QML2_IMPORT_PATH", None)
    return env


def open_path(target):
    """a folder in the file manager, a file in its program, a link in the browser"""
    if WINDOWS:
        os.startfile(target)
        return
    command = ["open", target] if MAC else ["xdg-open", target]
    subprocess.Popen(command, env=_clean_environment(), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def open_link(url):
    if LINUX:
        open_path(url)
    else:
        import webbrowser

        webbrowser.open(url)


# ------------------------------------------------------------------ staying awake

_awake_lock = threading.Lock()
_awake_count = 0
_awake_process = None


def keep_awake(on):
    """
    a profile of 500 videos takes the best part of an hour on a cpu, and a
    laptop that goes to sleep after fifteen minutes stops it halfway. this
    tells the system the machine is busy, for as long as the work runs (the
    screen can still turn off).
    """
    if WINDOWS:
        # per thread on windows: each worker asks for itself
        try:
            import ctypes

            ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))
        except Exception:
            pass
        return
    # elsewhere one helper process holds the lock for every running job
    global _awake_count, _awake_process
    with _awake_lock:
        _awake_count = _awake_count + 1 if on else max(0, _awake_count - 1)
        if _awake_count and _awake_process is None:
            _awake_process = _start_inhibitor()
        elif not _awake_count and _awake_process is not None:
            try:
                _awake_process.terminate()
            except Exception:
                pass
            _awake_process = None


def _start_inhibitor():
    if MAC:
        command = ["caffeinate", "-i", "-w", str(os.getpid())]
    else:
        command = ["systemd-inhibit", "--what=idle:sleep", "--who=Syllark",
                   "--why=Transcribing", "--mode=block", "sleep", "infinity"]
    try:
        return subprocess.Popen(command, env=_clean_environment(), stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return None


# ------------------------------------------------------------------ theme and language


def system_dark_theme():
    """whether the system is in dark mode; dark when it cannot tell"""
    if WINDOWS:
        try:
            import winreg

            k = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            light, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
            return not light
        except Exception:
            return True
    if MAC:
        # the key only exists in dark mode
        value = _read(["defaults", "read", "-g", "AppleInterfaceStyle"])
        return value is None or "dark" in value.lower()
    value = _read(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"])
    if value and "default" not in value:
        return "dark" in value
    value = _read(["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"])
    if value:
        return "dark" in value.lower()
    try:
        with open(os.path.join(os.path.expanduser("~"), ".config", "kdeglobals"), encoding="utf-8") as f:
            for line in f:
                if line.startswith("ColorScheme="):
                    return "dark" in line.lower()
    except OSError:
        pass
    return True


def user_locale():
    """the language the system is set to, as a code like it-IT; '' if unknown"""
    if WINDOWS:
        try:
            import ctypes

            buffer = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buffer, len(buffer)):
                return buffer.value
        except Exception:
            pass
        return ""
    if MAC:
        value = _read(["defaults", "read", "-g", "AppleLanguages"])
        if value:
            for part in value.replace("(", " ").replace(")", " ").replace(",", " ").split():
                part = part.strip('"')
                if part:
                    return part
    for name in ("LC_ALL", "LC_MESSAGES", "LANGUAGE", "LANG"):
        value = os.environ.get(name, "")
        value = value.split(":")[0].split(".")[0]
        if value and value not in ("C", "POSIX"):
            return value.replace("_", "-")
    return ""


def _read(command):
    try:
        result = subprocess.run(command, env=_clean_environment(), capture_output=True,
                                text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


# ------------------------------------------------------------------ one window only

_instance = None


def already_running(title):
    """
    a second double click on the shortcut used to open a second window, which
    loaded a second copy of whisper next to the first. now it brings the
    window that is already open to the front (where the system lets it) and
    leaves.
    """
    global _instance
    if WINDOWS:
        try:
            import ctypes

            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.CreateMutexW.restype = ctypes.c_void_p
            _instance = k.CreateMutexW(None, False, "Local\\tiktok-transcriber")
            if ctypes.get_last_error() != 183:  # ERROR_ALREADY_EXISTS
                return False
            u = ctypes.windll.user32
            hwnd = u.FindWindowW(None, title)
            if hwnd:
                u.ShowWindow(hwnd, 9)  # SW_RESTORE
                u.SetForegroundWindow(hwnd)
            return True
        except Exception:
            return False
    # a lock the system releases by itself when the process ends, even on a crash
    try:
        import fcntl

        folder = os.path.join(data_base(), storage_name(""))
        os.makedirs(folder, exist_ok=True)
        _instance = open(os.path.join(folder, "instance.lock"), "w")
        try:
            fcntl.flock(_instance, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        return False
    except Exception:
        return False


def message_box(text, title):
    """an error the user can see when there is no window and no console"""
    if WINDOWS:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)
        return
    if MAC:
        script = 'display alert %s message %s as critical' % (_quote(title), _quote(text))
        subprocess.run(["osascript", "-e", script], timeout=120)
        return
    for command in (["zenity", "--error", "--title", title, "--text", text],
                    ["kdialog", "--title", title, "--error", text],
                    ["notify-send", title, text]):
        try:
            subprocess.run(command, env=_clean_environment(), timeout=120)
            return
        except (OSError, subprocess.SubprocessError):
            continue
    raise OSError("no dialog program")


def _quote(text):
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'
