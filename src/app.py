"""Syllark desktop window, settings, and a batched Python/WebView2 bridge."""

import gc
import json
import os
import queue
import re
import sys
import threading
import time
import traceback

# where ui.html, vendor/ and the icon are: next to this file, or inside the
# .exe's runtime folder when it runs as the built program
HERE = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
# installed with pip, the modules sit in a package folder of their own
if HERE not in sys.path:
    sys.path.insert(0, HERE)
TITLE = "Syllark"

import desktop  # noqa: E402  (only the standard library: safe before the crash handler)

# a windowed .exe (and pythonw) has no console: sys.stderr is None, and the
# first library that writes a progress bar there (the model download does)
# crashes on it. give them somewhere harmless to write.
for _name in ("stdout", "stderr"):
    if getattr(sys, _name) is None:
        setattr(sys, _name, open(os.devnull, "w", encoding="utf-8"))


def _report_crash(text):
    """
    under pythonw there is no console: a crash at startup used to mean that
    double clicking the shortcut simply did nothing. now it leaves a file and
    says so.
    """
    home = os.path.join(desktop.data_base(), desktop.storage_name("TikTok Transcriber"))
    path = os.path.join(home, "crash.log")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(time.strftime("\n=== %Y-%m-%d %H:%M:%S ===\n") + text)
    except OSError:
        path = "(could not write the crash log)"
    try:
        try:
            from localization import translate
            with open(os.path.join(home, "settings.json"), encoding="utf-8") as f:
                language = json.load(f).get("ui_language", "en")
            tr = lambda key, **params: translate(key, language, **params)
        except Exception:
            tr = lambda key, **params: key.format(**params)
        desktop.message_box(
            tr("the app could not start.") + "\n\n" + text.strip().splitlines()[-1] + "\n\n"
            + tr("details in {p0}", p0=path), TITLE)
    except Exception:
        print(text, file=sys.stderr)


try:
    desktop.prepare_window_engine()
    import webview

    import tiktok_core as core
except Exception:
    _report_crash(traceback.format_exc())
    raise

DEFAULT_FOLDER = core.default_output_folder()

DATA_DIR = core.DATA_DIR
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
WEBVIEW_CACHE = os.path.join(DATA_DIR, "webview")

# carry over settings written by older versions, wherever they were
for _old in (os.path.join(DATA_DIR, "impostazioni.json"),
             os.path.join(core.PROGRAM_DIR, "impostazioni.json"),
             os.path.join(core.PROGRAM_DIR, "settings.json")):
    if os.path.exists(_old) and not os.path.exists(SETTINGS_FILE):
        try:
            os.replace(_old, SETTINGS_FILE)
        except OSError:
            pass

window = None
_maximized = False
_hwnd = None


# ------------------------------------------------------------------ events


class Bridge:
    """
    batches events and sends them to the javascript in packets.

    three things in here used to bring the window to its knees with two
    hundred videos, and they are the reason it "clogged up":

    1. evaluate_js. pywebview implements it by wrapping the script inside an
       eval("...") with escaped quotes, and then has the result serialised
       back to json to read it in python. on a packet of a few hundred
       kilobytes that means escaping the string in python, having javascript
       reparse it twice and then parsing the answer back. run_js does the same
       thing with none of that: the script goes out as it is and nobody
       reports anything back.

    2. the buffer had neither a floor nor a memory. progress events are
       SNAPSHOTS: only the last one matters. before, they all piled up, so if
       the javascript slowed down for a moment the buffer grew, the next
       packet was bigger, the javascript slowed down more and from there it
       never recovered. now a new progress event overwrites the old one for
       the same video instead of queueing behind it.

    3. the interval was pinned at 80 ms even when the javascript took 300 ms
       to digest the previous packet. now it waits at least as long as the
       last one took.
    """

    # past this ceiling something really did go wrong: drop the oldest of the
    # expendable events instead of letting memory explode.
    # after trimming it goes down to FLOOR, not to the ceiling: otherwise the
    # first event after a trim triggers another one, and trimming costs as
    # much as the whole queue. this way another thousand events have to arrive
    # before paying that price again.
    CEILING = 3000
    FLOOR = 2000

    def __init__(self, interval=0.08, max_wait=0.5):
        self.pending = []
        self.index = {}          # merge key -> position inside pending
        self.lock = threading.Lock()
        self.interval = interval
        self.max_wait = max_wait
        self.wait = interval
        self.running = False
        self.dropped = 0

    # ---- which events can be overwritten instead of appended ----

    @staticmethod
    def _key(e):
        kind = e.get("type")
        if kind == "percent":
            return ("percent", e.get("id"))
        if kind == "progress":
            return ("progress",)
        # in the gallery only updates of the SAME state get merged:
        # "downloading 12%" and "downloading 48%" yes, "downloading" and
        # "done" no, otherwise a card would stay one state behind
        if kind == "gallery" and e.get("pct") is not None:
            return ("gallery", e.get("id"), e.get("state"))
        return None

    def start(self):
        with self.lock:
            if self.running:
                return
            self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def send(self, event):
        key = self._key(event)
        with self.lock:
            if key is not None:
                where = self.index.get(key)
                if where is not None:
                    self.pending[where] = event
                    return
                self.index[key] = len(self.pending)
            self.pending.append(event)
            if len(self.pending) > self.CEILING:
                self._trim()

    def _trim(self):
        """
        we are past the ceiling: keep every log and state change (they are the
        story of what happened) and drop the oldest progress events, which
        have already been superseded by the ones after them.

        if that still leaves too much, cut the oldest: those count as really
        lost, and the user gets told instead of them vanishing quietly.
        """
        kept = [e for e in self.pending if e.get("type") not in ("percent", "progress")]
        if len(kept) > self.FLOOR:
            kept = kept[-self.FLOOR:]
        self.dropped += len(self.pending) - len(kept)
        self.pending = kept
        self._reindex()

    def _reindex(self):
        self.index = {}
        for i, e in enumerate(self.pending):
            k = self._key(e)
            if k is not None:
                self.index[k] = i

    def _take(self):
        with self.lock:
            if not self.pending and not self.dropped:
                return None
            packet, self.pending, self.index = self.pending, [], {}
            if self.dropped:
                # do not let them disappear quietly: if updates were thrown
                # away the user should at least know about it
                packet.append({
                    "type": "log",
                    "text": f"the window could not keep up: {self.dropped} updates dropped "
                            "(the transcripts are unaffected, they carry on)",
                    "level": "warn",
                })
                self.dropped = 0
            return packet

    def _ship(self, packet):
        """
        the json is already valid javascript, so it goes straight in as an
        argument: no eval, no string to reparse.

        the only two characters json lets through that javascript will not
        accept inside source are U+2028 and U+2029 (unicode line separators).
        they show up in tiktok captions, and without this line the packet
        becomes a syntax error and vanishes without a trace.
        """
        text = json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
        text = text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
        window.run_js("window.receiveEvents(" + text + ")")

    def _loop(self):
        while self.running:
            time.sleep(self.wait)
            packet = self._take()
            if not packet:
                self.wait = self.interval
                continue
            t0 = time.monotonic()
            try:
                if window:
                    self._ship(packet)
            except Exception:
                # the window may not be ready yet, or already closed: in both
                # cases there is nothing to save
                pass
            # if the javascript took longer than the interval, give it that
            # much time on the next round: it is the only thing preventing the
            # spiral where packets arrive faster than they are digested
            elapsed = time.monotonic() - t0
            self.wait = min(self.max_wait, max(self.interval, elapsed))

    def flush_now(self):
        packet = self._take()
        if packet and window:
            try:
                self._ship(packet)
            except Exception:
                pass


bridge = Bridge()

# the engine says how the first-start downloads are going (the model, the
# graphics card libraries): straight to the window, wherever they started
core.setup_listener = lambda e: bridge.send({"type": "setup", **e})


# ------------------------------------------------------------------ system bits


keep_awake = desktop.keep_awake


def flash_taskbar():
    """a long run that finishes while you are elsewhere blinks in the taskbar"""
    if desktop.MAC:
        try:
            from AppKit import NSApplication

            # NSInformationalRequest (10): one bounce of the dock icon
            NSApplication.sharedApplication().requestUserAttention_(10)
        except Exception:
            pass
        return
    if not _hwnd:
        return
    try:
        import ctypes
        from ctypes import wintypes

        class FLASHWINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND),
                        ("dwFlags", wintypes.DWORD), ("uCount", wintypes.UINT),
                        ("dwTimeout", wintypes.DWORD)]

        u = ctypes.windll.user32
        u.GetForegroundWindow.restype = wintypes.HWND
        if u.GetForegroundWindow() == _hwnd:
            return
        # FLASHW_ALL (3) | FLASHW_TIMERNOFG (12): until the window comes back
        info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), _hwnd, 3 | 12, 0, 0)
        u.FlashWindowEx(ctypes.byref(info))
    except Exception:
        pass


# ------------------------------------------------------------------ api


class Workshop:
    """
    keeps whisper loaded once and runs two separate queues: one for downloads,
    one for transcriptions.

    separate on purpose: downloading is network, transcribing is gpu. if they
    shared a queue, asking for an mp4 while it transcribes would leave you
    waiting for nothing.

    the model lives here for the whole session, and the whole-profile run
    borrows it too: before, a run after a few clicks in the gallery loaded a
    second copy, ten seconds and three gigabytes of graphics memory later.
    """

    DOWNLOADERS = 3

    def __init__(self):
        self._engine = None
        self._lock = threading.Lock()
        self._collection_lock = threading.Lock()
        self.transcribe_queue = queue.Queue()
        self.download_queue = queue.Queue()
        self.cancelled = set()
        # what is already queued: without these, cancelling and then clicking
        # again leaves the old task in the queue (which meanwhile became valid
        # again) plus the new one, and the video gets done twice
        self.queued_transcribe = set()
        self.queued_download = set()
        self._queue_lock = threading.Lock()
        self._started = False

    # --------------------------------------------------------- engines

    def engine(self, log, model=None):
        """the model loaded once and reused: reloading it costs 10 seconds"""
        model = core.model_name(model)
        with self._lock:
            if self._engine is not None and self._engine.name != model:
                log(f"switching the model to {model}")
                # whatever is still transcribing keeps its own reference:
                # the memory goes back when it finishes
                self._engine = None
                gc.collect()
            if self._engine is None:
                self._engine = core.Engine(model, log=log)
            return self._engine

    def transcribers(self, model=None):
        """how many actually run: the engine's own number when it is loaded,
        otherwise the number that would be chosen right now"""
        e = self._engine
        if e:
            return e.workers
        if core.model_name(model) == "qwen3-asr":
            return 1
        return core.GPU_TRANSCRIBERS if core.gpu_available()[0] else core.TRANSCRIBERS

    # --------------------------------------------------------- queues

    def start(self, api):
        with self._queue_lock:
            if self._started:
                return
            self._started = True
        for _ in range(self.DOWNLOADERS):
            threading.Thread(target=self._download_loop, args=(api,), daemon=True).start()
        # the transcribers start on the first job, once we know how many fit
        threading.Thread(target=self._first_transcriber, args=(api,), daemon=True).start()

    def _first_transcriber(self, api):
        task = self.transcribe_queue.get()
        if task is None:
            return
        n = core.GPU_TRANSCRIBERS
        try:
            e = self.engine(lambda t, l=None: api._log(t, l), api._model())
            n = e.workers
        except Exception as e:
            # no silence here: if the engine fails to load the user has to
            # know why, otherwise all they see is transcriptions failing
            api._log(f"the transcription engine did not load: {e}", "err")
        for _ in range(max(0, n - 1)):
            threading.Thread(target=self._transcribe_loop, args=(api,), daemon=True).start()
        self._run_transcription(api, task)
        self._transcribe_loop(api)

    def _transcribe_loop(self, api):
        while True:
            task = self.transcribe_queue.get()
            if task is None:
                return
            self._run_transcription(api, task)

    def _download_loop(self, api):
        while True:
            task = self.download_queue.get()
            if task is None:
                return
            self._run_download(api, task)

    def queue_transcription(self, video, api):
        vid = str(video.get("id"))
        bridge.start()
        self.start(api)
        with self._queue_lock:
            self.cancelled.discard(vid)
            already = vid in self.queued_transcribe
            self.queued_transcribe.add(vid)
        api._card(vid, "queued")
        if already:
            # there is already a task queued for this video (maybe you
            # cancelled it a moment ago): that one is plenty
            return
        self.transcribe_queue.put(video)

    def queue_download(self, video, api):
        vid = str(video.get("id"))
        bridge.start()
        self.start(api)
        with self._queue_lock:
            self.cancelled.discard(vid)
            already = vid in self.queued_download
            self.queued_download.add(vid)
        api._card(vid, "queued_mp4")
        if already:
            return
        self.download_queue.put(video)

    def cancel(self, vid):
        """
        a queued video is dropped when its turn comes; one already being
        downloaded is stopped right there; one being transcribed finishes the
        transcription (whisper cannot be interrupted) and is thrown away.
        before, cancel only worked on the queued ones and on the others the
        button did nothing at all.
        """
        with self._queue_lock:
            self.cancelled.add(str(vid))

    def _is_cancelled(self, vid):
        with self._queue_lock:
            return vid in self.cancelled

    # --------------------------------------------------------- work

    def _run_download(self, api, video):
        vid = str(video.get("id"))
        with self._queue_lock:
            self.queued_download.discard(vid)
            cancelled = vid in self.cancelled
        if cancelled:
            api._card(vid, "")
            return
        keep_awake(True)
        try:
            browser = None
            folder = os.path.join(api._profile_folder(video.get("handle")), "video")
            api._card(vid, "downloading_mp4", pct=0)
            path = core.download_full_video(
                video.get("url"), folder, browser,
                on_progress=lambda p: api._card(vid, "downloading_mp4", pct=p),
                cancelled=lambda: self._is_cancelled(vid),
            )
            api._card(vid, "downloaded", file=path)
            api._log(f"mp4 saved: {os.path.basename(path)}", "ok")
        except core.Cancelled:
            api._card(vid, "")
            api._log(f"mp4 cancelled ({vid})", "warn")
        except Exception as e:
            api._card(vid, "error", message=core._explain_error(str(e))[:140])
            api._log(f"mp4 not downloaded ({vid}): {core._explain_error(str(e))}", "warn")
        finally:
            keep_awake(False)

    def _run_transcription(self, api, video):
        vid = str(video.get("id"))
        with self._queue_lock:
            self.queued_transcribe.discard(vid)
            cancelled = vid in self.cancelled
        if cancelled:
            api._card(vid, "")
            return
        keep_awake(True)
        try:
            browser = None
            options = {
                "language": api._setting("language", "auto"),
                "ui_language": api._ui_language(),
                "format": api._setting("format", "md"),
                "timestamps": api._setting("timestamps", False),
            }
            engine = self.engine(lambda t, l=None: api._log(t, l), api._model())
            folder = api._profile_folder(video.get("handle"))
            core.transcribe_one(
                video, folder, browser, engine, options,
                on_state=lambda s, **k: api._card(vid, s, **k),
                cancelled=lambda: self._is_cancelled(vid),
            )
            # the "all in one" file follows the gallery too, once the queue
            # has emptied: rebuilding it after every single click is wasted
            if self.transcribe_queue.empty():
                with self._collection_lock:
                    try:
                        core.rebuild_collection(folder, video.get("handle"),
                                                ui_language=api._ui_language())
                    except OSError:
                        pass
        except core.Cancelled:
            api._card(vid, "")
            api._log(f"transcription cancelled ({vid})", "warn")
        except Exception as e:
            api._card(vid, "error", message=core._explain_error(str(e))[:140])
            api._log(f"transcription failed ({vid}): {core._explain_error(str(e))}", "warn")
        finally:
            keep_awake(False)


class Api:
    def __init__(self):
        self.job = None
        self.thread = None
        self.workshop = Workshop()
        self.exploration = None
        self.stop_exploration = threading.Event()
        self._settings_lock = threading.Lock()
        self._settings = None          # settings kept in memory

    # --- shortcuts for sending events to the window ---

    @staticmethod
    def _log(text, level="info"):
        bridge.send({"type": "log", "text": str(text), "level": level or "info"})

    @staticmethod
    def _card(video_id, state, **extra):
        bridge.send({"type": "gallery", "id": str(video_id), "state": state, **extra})

    # ---------------------------------------------------------- startup

    def initial_state(self):
        model = self._model()
        natural_gpu, whisper_gpu = core.gpu_available("qwen3-asr"), core.gpu_available()
        device_for = lambda name: natural_gpu if name == "qwen3-asr" else whisper_gpu
        return {
            "folder": self._folder(),
            "model": model,
            "models": [
                {"id": k, "label": m["label"], "technical": m["technical"], "size": m["size"], "note": m["note"],
                 "downloaded": core.model_downloaded(k), "gpu": device_for(k)[0]}
                for k, m in core.MODELS.items()
            ],
            "language": self._setting("language", "auto"),
            "ui_language": self._ui_language(),
            "format": self._setting("format", "md"),
            "timestamps": self._setting("timestamps", False),
            "resume": self._setting("resume", True),
            "limit": self._setting("limit", None),
            "theme": saved_theme() or "",
            "motion": self._setting("motion", "quiet"),
            "gpu": dict(zip(("ok", "why"), device_for(model))),
            "languages": [{"id": k, "name": v} for k, v in core.LANGUAGES.items()],
            "whisper": core.whisper_installed(),
            "cpu": os.cpu_count() or 4,
        }

    # ---------------------------------------------------------- settings

    # Serialize settings updates and replace the on-disk snapshot atomically.

    # older versions wrote the keys in italian, and two of them belonged to the
    # speaker recognition that no longer exists. without this the file reads as
    # a pile of unknown keys and every setting silently goes back to default,
    # output folder included.
    OLD_KEYS = {                                              # legacy
        "cartella": "folder",                                 # legacy
        "lingua": "language", "formato": "format",            # legacy
        "timestamp": "timestamps", "riprendi": "resume",      # legacy
        "limite": "limit",                                    # legacy
    }
    # "model" was written by every run but never read: it always said
    # large-v3 whatever happened. the real choice lives in "whisper_model"
    DROPPED_KEYS = ("voci", "quante_voci", "modello",         # legacy
                    "speakers", "speaker_count", "model", "browser")

    def _read_disk(self):
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {}
            for old, new in self.OLD_KEYS.items():
                if old in data:
                    data.setdefault(new, data[old])
                    del data[old]
            for gone in self.DROPPED_KEYS:
                data.pop(gone, None)
            return data
        except Exception:
            return {}

    def _all_settings(self):
        with self._settings_lock:
            if self._settings is None:
                self._settings = self._read_disk()
            return dict(self._settings)

    def _setting(self, key, fallback):
        value = self._all_settings().get(key, fallback)
        return fallback if value is None else value

    def _model(self):
        return core.model_name(self._setting("whisper_model", core.DEFAULT_MODEL))

    def _ui_language(self):
        from localization import normalize
        saved = self._setting("ui_language", "")
        if saved:
            return normalize(saved)
        system = desktop.user_locale()
        return normalize(system) if system else "en"

    def _folder(self):
        """
        the output folder, as long as it can exist on THIS computer.

        the settings travel with the program (the data folder sits next to
        it), so a folder saved on another pc — another user name, a drive
        letter that is not there — came back as is, and the first run died
        trying to create C:\\Users\\somebody-else\\Documents.
        """
        path = self._setting("folder", DEFAULT_FOLDER)
        if not path:
            return DEFAULT_FOLDER
        if os.path.isdir(path):
            return path
        parent = os.path.dirname(os.path.normpath(path))
        return path if parent and os.path.isdir(parent) else DEFAULT_FOLDER

    def save_settings(self, data):
        try:
            with self._settings_lock:
                if self._settings is None:
                    self._settings = self._read_disk()
                self._settings.update({k: v for k, v in (data or {}).items() if k not in self.DROPPED_KEYS})
                text = json.dumps(self._settings, indent=2, ensure_ascii=False)
                os.makedirs(os.path.dirname(SETTINGS_FILE) or ".", exist_ok=True)
                temporary = SETTINGS_FILE + ".new"
                with open(temporary, "w", encoding="utf-8") as f:
                    f.write(text)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temporary, SETTINGS_FILE)   # atomic: either the old or the new
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def pick_folder(self, current=None):
        try:
            choice = window.create_file_dialog(
                webview.FOLDER_DIALOG, directory=current or DEFAULT_FOLDER
            )
        except Exception:
            return None
        if not choice:
            return None
        p = choice[0] if isinstance(choice, (list, tuple)) else choice
        return os.path.normpath(p)

    def open_folder(self, path):
        path = path or self._folder()
        try:
            os.makedirs(path, exist_ok=True)
            desktop.open_path(path)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def open_link(self, url):
        if str(url or "").startswith(("http://", "https://")):
            desktop.open_link(url)
        return {"ok": True}

    def open_file(self, path):
        try:
            if path and os.path.exists(path):
                desktop.open_path(path)
                return {"ok": True}
            return {"ok": False, "error": "the file is not there"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------------------------------------------------------- views

    def history(self):
        """the profiles already extracted, read from the output folder"""
        base = self._folder()
        out = []
        try:
            for name in os.listdir(base):
                folder = os.path.join(base, name)
                if not os.path.isdir(folder):
                    continue
                # transcripts only: there is also the "video" subfolder in
                # there, the summary files, maybe a desktop.ini, and counting
                # them as transcripts made it say "3 videos" where there were two
                transcripts = core.transcripts_on_disk(folder)
                if not transcripts:
                    continue
                # the size has to be taken recursively, otherwise the mp4s
                # inside "video" weigh nothing and the card says 300 bytes when
                # there are five million on disk
                size = 0
                newest = 0
                for root, _, files in os.walk(folder):
                    for f in files:
                        try:
                            st = os.stat(os.path.join(root, f))
                            size += st.st_size
                            newest = max(newest, st.st_mtime)
                        except OSError:
                            pass
                out.append({
                    "handle": name,
                    "videos": len(transcripts),
                    "size": size,
                    "when": time.strftime("%Y-%m-%d %H:%M", time.localtime(newest)) if newest else "",
                    "ts": newest,
                    "path": folder,
                })
        except FileNotFoundError:
            pass
        except Exception as e:
            return {"ok": False, "error": str(e)[:160], "items": []}
        out.sort(key=lambda x: x["ts"], reverse=True)
        return {"ok": True, "items": out, "base": base}

    # ---------------------------------------------------------- gallery

    def _profile_folder(self, handle):
        return core.profile_folder(self._folder(), handle)

    @staticmethod
    def _downloaded_videos(folder):
        out = {}
        try:
            for f in os.listdir(folder):
                m = re.match(r"^(\d{6,})\s*-\s*", f)
                if m and f.lower().endswith((".mp4", ".webm", ".mov", ".mp3", ".m4a", ".aac", ".opus", ".ogg")):
                    out[m.group(1)] = os.path.join(folder, f)
        except OSError:
            pass
        return out

    def explore(self, profile, limit=None):
        """
        starts immediately and sends the videos in batches as they arrive,
        instead of making you wait twenty seconds with a frozen window.
        """
        if self.exploration and self.exploration.is_alive():
            self.stop_exploration.set()
            self.exploration.join(timeout=5)
            if self.exploration.is_alive():
                # do not start on top of the previous one: the two streams
                # would fill the same grid with two different profiles
                return {"ok": False, "error": "still stopping the previous exploration, "
                                              "try again in a couple of seconds"}
        # the thread keeps ITS own event: if another one starts while this is
        # closing, "stopped" has to tell the truth about this one
        halt = threading.Event()
        self.stop_exploration = halt
        bridge.start()

        def work():
            try:
                url, _, video_link = core.normalize_profile(profile)
                browser = None
                state = {"folder": None, "done": {}, "downloaded": {}}

                def head(d):
                    folder = self._profile_folder(d["handle"])
                    state["folder"] = folder
                    state["done"] = core.transcripts_on_disk(folder)
                    state["downloaded"] = self._downloaded_videos(os.path.join(folder, "video"))
                    bridge.send({"type": "gal_start", "handle": d["handle"], "folder": folder})

                def batch(group, total):
                    for v in group:
                        v["done"] = v["id"] in state["done"]
                        v["file"] = state["done"].get(v["id"])
                        v["downloaded"] = v["id"] in state["downloaded"]
                        v["video_file"] = state["downloaded"].get(v["id"])
                    bridge.send({"type": "gal_batch", "videos": group, "total": total})

                r = core.explore_stream(
                    url, browser, limit=int(limit) if limit else None,
                    on_head=head, on_batch=batch,
                    stopped=halt.is_set,
                    video_link=video_link,
                )
                bridge.send({"type": "gal_done", "total": r["total"],
                             "stopped": halt.is_set()})
            except core.TikTokError as e:
                bridge.send({"type": "gal_error", "error": str(e)})
            except Exception as e:
                bridge.send({"type": "gal_error", "error": core._explain_error(str(e))})

        self.exploration = threading.Thread(target=work, daemon=True)
        self.exploration.start()
        return {"ok": True}

    def stop_explore(self):
        self.stop_exploration.set()
        return {"ok": True}

    # ---- queues: downloads and single transcriptions no longer block

    def download_mp4(self, video):
        self.workshop.queue_download(dict(video), self)
        return {"ok": True}

    def transcribe_one(self, video):
        self.workshop.queue_transcription(dict(video), self)
        return {"ok": True}

    def cancel_one(self, video_id):
        self.workshop.cancel(str(video_id))
        return {"ok": True}

    def about(self):
        import importlib.metadata as md

        def version(name):
            try:
                return md.version(name)
            except Exception:
                return "not installed"

        models = [{"id": k, "label": m["label"], "technical": m["technical"], "downloaded": core.model_downloaded(k),
                   "size": core.model_size_on_disk(k), "selected": k == self._model()}
                  for k, m in core.MODELS.items()]
        gpu_ok, gpu_why = core.gpu_available(self._model())
        active_engine = self.workshop._engine
        if active_engine is not None and active_engine.name == self._model():
            gpu_ok = active_engine.device != "cpu"
            gpu_why = active_engine.device

        return {
            "python": sys.version.split()[0],
            "cpu": os.cpu_count() or 0,
            # the real ones: if the engine is already loaded, ask it, otherwise
            # say how many would be picked right now
            "transcribers": self.workshop.transcribers(self._model()),
            "threads": 0 if gpu_ok else (6 if self._model() == "qwen3-asr" else core.THREADS_EACH),
            "device": "graphics card" if gpu_ok else "processor",
            "downloaders": core.DOWNLOADERS,
            "packages": [
                {"name": "yt-dlp", "v": version("yt-dlp")},
                {"name": "curl_cffi", "v": version("curl_cffi")},
                {"name": "faster-whisper", "v": version("faster-whisper")},
                {"name": "transcribe-cpp", "v": version("transcribe-cpp")},
                {"name": "ctranslate2", "v": version("ctranslate2")},
                {"name": "pywebview", "v": version("pywebview")},
                {"name": "av", "v": version("av")},
            ],
            "models": models,
            "gpu": {"ok": gpu_ok, "why": gpu_why, "libraries": core.CUDA_DLLS},
            "cache": core.models_cache_dir(),
            "app_folder": core.PROGRAM_DIR,
            "data_folder": DATA_DIR,
        }

    # ---------------------------------------------------------- the job

    def start(self, options):
        if self.thread and self.thread.is_alive():
            return {"ok": False, "error": "it is already working"}

        options = dict(options or {})
        if not (options.get("profile") or "").strip():
            return {"ok": False, "error": "paste a profile link"}
        model = core.model_name(options.get("model") or self._model())
        options["model"] = model
        options["ui_language"] = options.get("ui_language") or self._ui_language()

        self.save_settings({
            **{k: options.get(k)
               for k in ("folder", "language", "ui_language", "format", "timestamps",
                         "resume", "limit")
               if k in options},
            "whisper_model": model,
        })

        bridge.start()
        self.job = core.Transcriber(
            options, bridge.send,
            engine=lambda log: self.workshop.engine(log, model),
        )
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        return {"ok": True}

    def _run(self):
        keep_awake(True)
        try:
            self.job.run()
        finally:
            keep_awake(False)
            time.sleep(0.2)
            bridge.flush_now()
            flash_taskbar()

    def stop(self):
        if self.job:
            self.job.stop.set()
            bridge.send({"type": "log", "text": "stopping, finishing what is in flight...",
                         "level": "warn"})
        return {"ok": True}

    # ---------------------------------------------------------- window

    # the window has no frame, so the three buttons in the top right corner
    # are mine to handle: windows does not draw them any more.

    def minimize(self):
        try:
            window.minimize()
        except Exception:
            pass
        return {"ok": True}

    def maximize(self):
        """
        the state comes from windows, it is not something to remember.

        it used to be a hand-kept boolean: maximising with a double click on
        the title bar, or with win+up, or by dragging the window to the top
        was enough, and from then on the button did the opposite of what you
        could see.
        """
        global _maximized
        try:
            _maximized = is_maximized()
            if _maximized:
                window.restore()
            else:
                window.maximize()
            _maximized = is_maximized()
        except Exception:
            pass
        return {"ok": True, "maximized": _maximized}

    @staticmethod
    def window_state():
        return {"maximized": is_maximized()}

    def close(self):
        try:
            if self.job:
                self.job.stop.set()
            self.stop_exploration.set()
            window.destroy()
        except Exception:
            os._exit(0)


def read_interface():
    """
    The page, with the local Nas stylesheet and scripts put inline.

    the window gets the html as a string, with no folder behind it, so a
    <script src="vendor/..."> would point at nothing. "</script" inside them
    (they have it in their usage comments) would end the tag early: written
    as "<\\/script" it means the same to javascript and nothing to html.
    """
    with open(os.path.join(HERE, "ui.html"), encoding="utf-8") as f:
        html = f.read()
    with open(os.path.join(HERE, "vendor", "nas.css"), encoding="utf-8") as f:
        html = html.replace('<link rel="stylesheet" href="vendor/nas.css">',
                            "<style>\n" + f.read() + "\n</style>")
    for name in ("orbi.js", "orbi-icons.js", "nas.js"):
        tag = f'<script src="vendor/{name}"></script>'
        try:
            with open(os.path.join(HERE, "vendor", name), encoding="utf-8") as f:
                code = f.read().replace("</script", "<\\/script")
        except OSError:
            if name == "nas.js":
                raise
            code = "/* vendor/%s is missing: the page works, without Orbi */" % name
        html = html.replace(tag, "<script>\n" + code + "\n</script>")
    locale_dir = os.path.join(HERE, "locales")
    with open(os.path.join(locale_dir, "languages.json"), encoding="utf-8") as f:
        languages = json.load(f)
    catalogs = {}
    for language in languages:
        with open(os.path.join(locale_dir, language["code"] + ".json"), encoding="utf-8") as f:
            catalogs[language["code"]] = json.load(f)
    with open(os.path.join(HERE, "i18n.js"), encoding="utf-8") as f:
        code = f.read()
    data = "window.APP_LANGUAGES=" + json.dumps(languages, ensure_ascii=False) + ";"
    with open(os.path.join(locale_dir, "plurals.json"), encoding="utf-8") as f:
        data += "window.APP_PLURALS=" + json.dumps(json.load(f), ensure_ascii=False) + ";"
    data += "window.APP_TRANSLATIONS=" + json.dumps(catalogs, ensure_ascii=False) + ";"
    html = html.replace('<script src="i18n.js"></script>',
                        "<script>\n" + (data + code).replace("</script", "<\\/script") + "\n</script>")
    with open(os.path.join(HERE, "controls.js"), encoding="utf-8") as f:
        html = html.replace('<script src="controls.js"></script>',
                            "<script>\n" + f.read().replace("</script", "<\\/script") + "\n</script>")
    if not desktop.WINDOWS:
        # the system draws the window's buttons there: the page hides its own
        html = html.replace("<body>", '<body data-frame="native">', 1)
    return html


def saved_theme():
    """the theme chosen with the theme button, if any: "dark", "light" or None"""
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            theme = json.load(f).get("theme")
        return theme if theme in ("dark", "light") else None
    except Exception:
        return None


def dark_theme():
    """the theme the window opens in: the saved choice, otherwise the system's"""
    theme = saved_theme()
    return system_dark_theme() if theme is None else theme == "dark"


system_dark_theme = desktop.system_dark_theme


def handle(w=None):
    """
    the native window handle.

    careful: Handle is a .NET IntPtr, int() chokes on it.
    """
    if w is None and _hwnd:
        return _hwnd
    w = w or window
    raw = w.native.Handle
    return raw.ToInt64() if hasattr(raw, "ToInt64") else int(raw)


def is_maximized():
    """ask windows: it is the only one that really knows"""
    if not desktop.WINDOWS:
        return _maximized
    try:
        import ctypes

        return bool(ctypes.windll.user32.IsZoomed(handle()))
    except Exception:
        return _maximized


def _set_icon(hwnd):
    """
    the window is pythonw's, so the taskbar showed python's icon. this puts
    the app's own icon on it, big (taskbar, alt+tab) and small (title).
    """
    import ctypes
    from ctypes import wintypes

    icon = os.path.join(HERE, "icon.ico")
    if not os.path.exists(icon):
        return
    u = ctypes.windll.user32
    u.LoadImageW.restype = wintypes.HANDLE
    u.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                             ctypes.c_int, ctypes.c_int, wintypes.UINT]
    u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    WM_SETICON, IMAGE_ICON, LR_LOADFROMFILE = 0x0080, 1, 0x0010
    for size, which in ((32, 1), (16, 0)):  # ICON_BIG, ICON_SMALL
        h = u.LoadImageW(None, icon, IMAGE_ICON, size, size, LR_LOADFROMFILE)
        if h:
            u.SendMessageW(hwnd, WM_SETICON, which, h)


def fix_window(w):
    """
    adjustments windows does not make by itself on a frameless window:

    1. it wants the title bar (the one left in the taskbar and in the
       previews) dark, otherwise it flashes white at startup.
    2. without a frame windows also removes WS_THICKFRAME, and with it goes
       the ability to resize by dragging the edges. put it back by hand:
       without a caption nothing is redrawn, but edge hit testing works again.
    3. the app's icon instead of python's.
    """
    global _hwnd
    try:
        import ctypes

        hwnd = _hwnd = handle(w)

        if dark_theme():
            for attribute in (20, 19):  # 20 on win10 1903+, 19 on older builds
                value = ctypes.c_int(1)
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
                ) == 0:
                    break

        GWL_STYLE, WS_THICKFRAME = -16, 0x00040000
        u = ctypes.windll.user32
        style = u.GetWindowLongW(hwnd, GWL_STYLE)
        if not style & WS_THICKFRAME:
            u.SetWindowLongW(hwnd, GWL_STYLE, style | WS_THICKFRAME)
            # SWP_NOMOVE|SWP_NOSIZE|SWP_NOZORDER|SWP_FRAMECHANGED
            u.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0004 | 0x0020)
        _set_icon(hwnd)
    except Exception as e:
        # no muted except: a failure here is invisible to the eye and would
        # stay hidden
        bridge.send({
            "type": "log",
            "text": f"could not tidy up the window: {type(e).__name__}: {e}",
            "level": "warn",
        })


def already_running():
    return desktop.already_running(TITLE)


def hide_runtime():
    """
    the built program is an .exe next to a "runtime" folder with everything
    it needs. a zip does not carry the hidden flag, so the program sets it
    itself: what you see in the folder is the .exe and nothing else.
    """
    if not core.FROZEN or not desktop.WINDOWS:
        return
    try:
        import ctypes

        folder = os.path.join(core.PROGRAM_DIR, "runtime")
        k = ctypes.windll.kernel32
        k.GetFileAttributesW.restype = ctypes.c_uint32
        attributes = k.GetFileAttributesW(folder)
        if attributes != 0xFFFFFFFF and not attributes & 0x2:   # FILE_ATTRIBUTE_HIDDEN
            k.SetFileAttributesW(folder, attributes | 0x2)
    except Exception:
        pass


def main():
    global window
    if already_running():
        return
    hide_runtime()
    if desktop.WINDOWS:
        try:
            import ctypes

            # its own taskbar group and icon, instead of being lumped with python
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("tiktok-transcriber")
        except Exception:
            pass
    threading.Thread(target=core.clean_temp, daemon=True).start()

    api = Api()
    window = webview.create_window(
        TITLE,
        html=read_interface(),
        js_api=api,
        width=1280,
        height=860,
        min_size=(1000, 680),
        # windows gets the app's own title bar. macos and linux keep the
        # system's: the buttons people expect there, and wayland does not let
        # a program move its own window by hand anyway.
        frameless=desktop.WINDOWS,
        easy_drag=False,  # drag from the title bar only, not from the whole window
        resizable=True,
        # the `fondo` of the Nas design system, so nothing flashes before the
        # page has drawn itself
        background_color="#1B2632" if dark_theme() else "#EEE9DF",
        text_select=True,  # the css decides what is selectable, so the log can be copied
    )
    if desktop.WINDOWS:
        window.events.shown += lambda: fix_window(window)
    else:
        window.events.maximized += lambda: _remember_maximized(True)
        window.events.restored += lambda: _remember_maximized(False)
    # The chosen model/libraries download on first use after public discovery.
    # Opening Options must not start downloading the default before the user
    # can choose a smaller model, or before an invalid link has been rejected.
    bridge.start()
    webview.start(
        gui=window_engine(), debug=False, private_mode=False, storage_path=WEBVIEW_CACHE,
        icon=os.path.join(HERE, "icon.png") if desktop.LINUX else None,
    )


def _remember_maximized(state):
    global _maximized
    _maximized = state


def window_engine():
    """
    WebView2 on windows, the system's WebKit on macos. on linux the built
    bundle carries Qt; from source pywebview picks whichever of Qt and GTK is
    installed.
    """
    if desktop.WINDOWS:
        return "edgechromium"
    if desktop.LINUX and core.FROZEN:
        return "qt"
    return None


def run():
    """the `syllark` command and the built program both start here"""
    try:
        if len(sys.argv) in (4, 6) and sys.argv[1] == "--verify-runtime":
            from runtime_check import run as verify
            verify(*sys.argv[2:])
        elif len(sys.argv) == 2 and sys.argv[1] in ("--version", "-V"):
            print(f"{TITLE} {core.APP_VERSION}")
        else:
            main()
    except Exception:
        _report_crash(traceback.format_exc())
        raise


if __name__ == "__main__":
    run()
