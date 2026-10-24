"""Public TikTok discovery, local speech recognition, queues, and transcript exports."""

import csv
import glob
import os
import queue
import re
import shutil
import site
import sys
import tempfile
import threading
import time
import unicodedata
import desktop
import tiktok_public
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit

# --- three things that must happen BEFORE importing anything whisper-related ---

# 1. huggingface tries to create symlinks and windows forbids that without
#    developer mode: the model download dies with "a required privilege is
#    not held by the client". this way it just copies instead.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
# 2. the plain http download: it writes the file as it goes, so the window can
#    show how far along it is, and a cut download picks up where it stopped
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

APP_NAME = "TikTok Transcriber"
APP_VERSION = "0.2.2"
STORAGE_NAME = "TikTok Transcriber"
FROZEN = bool(getattr(sys, "frozen", False))
# where the program is: next to the .exe, or the project folder (the one
# above src/) when it runs from the source
PROGRAM_DIR = (os.path.dirname(sys.executable) if FROZEN
               else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def data_dir():
    """
    where the settings, the window cache and the graphics card libraries live:
    %LOCALAPPDATA%/TikTok Transcriber, like any other windows program
    (~/Library/Application Support/TikTok Transcriber on macos, ~/.local/share/tiktok-transcriber
    on linux). the folder with the program stays as it was unpacked.

    older windows versions kept them in a "data" folder next to the program
    (or "dati", or in %LOCALAPPDATA% under another name): the first start
    moves them here, so no setting is lost.
    """
    base = desktop.data_base()
    home = os.path.join(base, desktop.storage_name(STORAGE_NAME))
    if desktop.WINDOWS and not os.path.isdir(home):
        for old in (os.path.join(PROGRAM_DIR, "data"), os.path.join(PROGRAM_DIR, "dati"),
                    os.path.join(PROGRAM_DIR, "src", "data"),
                    os.path.join(base, "tiktok-transcriber"), os.path.join(base, "trascrittore-tiktok")):
            if os.path.isdir(old):
                try:
                    os.replace(old, home)
                    break
                except OSError:
                    pass
    os.makedirs(home, exist_ok=True)
    return home


DATA_DIR = data_dir()
CUDA_DIR = os.path.join(DATA_DIR, "cuda")


# 3. ctranslate2 does not ship the cuda libraries: without these folders on
#    the dll search path the model LOADS fine and then dies on the first
#    inference with "Library cublas64_12.dll is not found".
_hooked_dirs = set()


def _hook_cuda():
    # deliberate order: the ones the app downloaded itself first, then the
    # environment's own, the per-user ones last. otherwise an old --user
    # install wins and you no longer know which library you are loading.
    roots = [CUDA_DIR]
    try:
        roots += list(site.getsitepackages() or [])
        roots.append(site.getusersitepackages())
    except Exception:
        pass

    if desktop.LINUX:
        return _preload_cuda(roots)
    if not desktop.WINDOWS:
        return []   # macos has no cuda
    hooked, seen = [], set()
    for root in roots:
        for d in sorted(glob.glob(os.path.join(root, "nvidia", "*", "bin"))):
            name = os.path.basename(os.path.dirname(d))
            # one library per name: two copies of the same dll on the search
            # path is just a way to make them fight
            if name in seen or not glob.glob(os.path.join(d, "*.dll")):
                continue
            seen.add(name)
            try:
                if d not in _hooked_dirs:
                    os.add_dll_directory(d)
                    # ctranslate2 loads cudnn's sub-libraries through PATH
                    os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
                    _hooked_dirs.add(d)
                hooked.append(name)
            except OSError:
                pass
    return sorted(hooked)


def _preload_cuda(roots):
    """
    linux reads LD_LIBRARY_PATH only when a program starts, so adding a folder
    later changes nothing. loading the libraries by hand works instead: when
    ctranslate2 or cudnn later ask for libcublas.so.12 by name, the system
    hands them the copy that is already in memory. a library that needs one
    not loaded yet fails the first round and gets another try.
    """
    import ctypes

    files, seen = [], set()
    for root in roots:
        for d in sorted(glob.glob(os.path.join(root, "nvidia", "*", "lib"))):
            name = os.path.basename(os.path.dirname(d))
            libraries = sorted(glob.glob(os.path.join(d, "lib*.so*")))
            if name in seen or not libraries:
                continue
            seen.add(name)
            files += [(name, f) for f in libraries if f not in _hooked_dirs]
    hooked = set()
    for _ in range(4):
        failed = []
        for name, path in files:
            try:
                ctypes.CDLL(path, mode=ctypes.RTLD_GLOBAL)
                _hooked_dirs.add(path)
                hooked.add(name)
            except OSError:
                failed.append((name, path))
        if not failed or len(failed) == len(files):
            break
        files = failed
    already = {os.path.basename(os.path.dirname(os.path.dirname(p))) for p in _hooked_dirs}
    return sorted(hooked | already)


CUDA_DLLS = _hook_cuda()

import yt_dlp  # noqa: E402  (after the environment above is in place)
from yt_dlp.utils import DownloadCancelled  # noqa: E402

# ------------------------------------------------------------------ constants


# All choices use bundled local engines and download their weights automatically.
# Accuracy depends on language/audio; no model promises an error-free transcript.
MODELS = {
    "qwen3-asr": {
        "label": "Natural",
        "technical": "Qwen3-ASR 1.7B",
        "size": "2.3 GB",
        "repo": "handy-computer/Qwen3-ASR-1.7B-gguf",
        "revision": "3555bd238a8572bbace3ebf60d23b036dc0a5dbe",
        "filename": "Qwen3-ASR-1.7B-Q8_0.gguf",
        "bytes": 2185030624,
        "note": "Natural sentences and punctuation. Block timestamps; slower without a graphics card.",
    },
    "large-v3-turbo": {
        "label": "Balanced",
        "technical": "Whisper large-v3 turbo",
        "size": "1.6 GB",
        "repo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
        "revision": "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf",
        "note": "Good accuracy and speed for most computers.",
    },
    "large-v3": {
        "label": "Thorough",
        "technical": "Whisper large-v3",
        "size": "3.1 GB",
        "repo": "Systran/faster-whisper-large-v3",
        "revision": "edaa852ec7e145841d8ffdb056a99866b5f0a478",
        "note": "Larger model for difficult audio. Takes more time and memory.",
    },
    "small": {
        "label": "Lightweight",
        "technical": "Whisper small",
        "size": "0.5 GB",
        "repo": "Systran/faster-whisper-small",
        "revision": "536b0662742c02347bc0e980a01041f333bce120",
        "note": "Smaller download and less memory. May miss more words.",
    },
}
DEFAULT_MODEL = "qwen3-asr"
LANGUAGE_MODEL = {
    "repo": "handy-computer/lang-id-voxlingua107-ecapa-gguf",
    "revision": "41cf26039e317c6b8883bf0a61b0785dc663fc26",
    "filename": "lang-id-voxlingua107-ecapa-Q8_0.gguf",
    "bytes": 26693632,
}


def model_name(name):
    """an unknown name (an old setting, a typo) falls back to the default"""
    return name if name in MODELS else DEFAULT_MODEL


LANGUAGES = {
    "auto": "detect from the video",
    "it": "italian",
    "en": "english",
    "es": "spanish",
    "fr": "french",
    "de": "german",
    "pt": "portuguese",
    "ru": "russian", "ar": "arabic", "hi": "hindi", "zh": "chinese",
    "ja": "japanese", "ko": "korean", "tr": "turkish", "id": "indonesian",
}

# lightest rendition with the h264 codec (bytevc1 is h265, slower to decode)
CLIP_FORMAT = "worst[vcodec^=h264][tbr>0]/worst[tbr>0]/worst"

# the mp4 the user keeps: h264 first. bytevc1 is h265, and stock windows
# cannot play it without a paid codec from the store, so "best" alone often
# meant a file that opens to a black screen.
FULL_FORMAT = "best[vcodec^=h264][ext=mp4]/best[ext=mp4]/best"

DOWNLOADERS = 4  # parallel downloads

# whisper: measured on this machine, four parallel transcriptions with a few
# threads each run 2.4x faster than a single transcription using every thread.
# ctranslate2 releases the gil and the model weights are shared between the
# workers, so memory does not double.
_CPU = os.cpu_count() or 4
TRANSCRIBERS = max(1, min(4, _CPU // 3))
THREADS_EACH = max(1, _CPU // TRANSCRIBERS)
GPU_TRANSCRIBERS = 2

# default output folder, and the italian name older versions used
OUTPUT_FOLDER_NAME = "TikTok Transcripts"
LEGACY_OUTPUT_FOLDER_NAME = "Trascrizioni TikTok"

# "123456789 - some title.md": the shape of every transcript file
TRANSCRIPT_RE = re.compile(r"^(\d{6,})\s*-\s*.*\.(md|txt)$", re.I)


documents_dir = desktop.documents_dir


def default_output_folder():
    """
    Documents/TikTok Transcripts, unless the old italian folder is the one
    that actually holds the user's transcripts.
    """
    documents = documents_dir()
    current = os.path.join(documents, OUTPUT_FOLDER_NAME)
    legacy = os.path.join(documents, LEGACY_OUTPUT_FOLDER_NAME)
    if os.path.isdir(legacy) and not os.path.isdir(current):
        return legacy
    return current


class TikTokError(Exception):
    pass


PUBLIC_UNAVAILABLE = "TikTok is not responding. Try again in a few minutes."


class Stopped(Exception):
    pass


class Cancelled(DownloadCancelled):
    """
    raised from inside a progress hook to abort a download halfway.
    it extends yt-dlp's own class because that one is let through untouched
    by every layer of yt-dlp, instead of being re-wrapped or reported.
    """


# ------------------------------------------------------------------ utility


class _QuietLogger:
    """
    yt-dlp prints its errors on stderr even with quiet=True. under pythonw
    there is no stderr at all, and in a terminal they just duplicate what the
    exception already says.
    """

    def debug(self, m):
        pass

    def info(self, m):
        pass

    def warning(self, m, **k):
        pass

    def error(self, m):
        pass


def safe_name(text, limit=70):
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    if len(text) > limit:
        text = text[:limit].rstrip(" .")
    return text or "untitled"


def one_line(text):
    """captions carry newlines: inside a heading or a csv cell they break it"""
    return re.sub(r"\s+", " ", str(text or "")).strip()


def mmss(seconds):
    seconds = int(max(0, seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def _atomic_write(path, text, encoding="utf-8", newline=None):
    """
    write next to the target and swap it in.

    resume treats any file named after a video as done: a transcript cut in
    half by a crash or a closed window used to be skipped forever after.
    """
    # one temporary name per thread: the gallery and a whole-profile run can
    # rewrite the same summary file at the same moment
    temporary = f"{path}.{threading.get_ident()}.partial"
    with open(temporary, "w", encoding=encoding, newline=newline) as f:
        f.write(text)
    os.replace(temporary, path)


def _tiktok_url(text):
    """Accept HTTP(S) URLs on TikTok hosts, without userinfo or custom ports."""
    if not text or any(c.isspace() or c == "\\" for c in text):
        return None
    candidate = text if re.match(r"https?://", text, re.I) else "https://" + text
    try:
        parts = urlsplit(candidate)
        host = parts.hostname or ""
        if (parts.scheme not in ("http", "https") or parts.username is not None
                or parts.password is not None or parts.port not in (None, 80, 443)
                or not (host == "tiktok.com" or host.endswith(".tiktok.com"))):
            return None
        return parts.geturl()
    except ValueError:
        return None


def _resolve_short_link(url):
    """Stop at a video's canonical redirect before the webpage can demand login."""
    from curl_cffi import requests

    current = _tiktok_url(url)
    if current is None:
        raise TikTokError("invalid public TikTok URL")
    try:
        with requests.Session(impersonate="chrome") as session:
            for _ in range(5):
                response = session.get(current, allow_redirects=False, timeout=12)
                location = response.headers.get("Location")
                if not location:
                    return current
                target = _tiktok_url(urljoin(current, location))
                if target is None:
                    return current
                if is_video_link(target):
                    return target
                current = target
    except requests.RequestsError:
        pass
    return current


def normalize_profile(text, _resolve=True):
    """Return (profile URL, label, video URL) for a handle or public TikTok URL."""
    t = (text or "").strip()
    if not t:
        raise TikTokError("you did not paste anything")

    if t.startswith("tiktokuser:"):
        return t, t, None

    if t.startswith("@"):
        handle = t[1:].split("?")[0].split("/")[0]
        if re.fullmatch(r"[\w.\-]{2,30}", handle):
            return f"https://www.tiktok.com/@{handle}", "@" + handle, None

    if re.fullmatch(r"[\w.\-]{2,30}", t):
        return f"https://www.tiktok.com/@{t}", "@" + t, None

    url = _tiktok_url(t)
    if url:
        parts = urlsplit(url)
        if _resolve and (parts.hostname in ("vm.tiktok.com", "vt.tiktok.com") or parts.path.startswith("/t/")):
            return normalize_profile(_resolve_short_link(url), _resolve=False)
        video = canonical_post(url) if is_video_link(url) else None
        match = re.match(r"/@([\w.\-]+)", parts.path)
        if match:
            handle = match.group(1)
            return f"https://www.tiktok.com/@{handle}", "@" + handle, video
        return url, url, None

    raise TikTokError(f"'{t[:60]}' does not look like a tiktok profile")


_POST_PATH = re.compile(r"/@([\w.\-]+)/(?:video|photo)/(\d+)/?")


def is_video_link(text):
    """one post: a video, or a photo post with its sound"""
    url = _tiktok_url(str(text or ""))
    return bool(url and _POST_PATH.fullmatch(urlsplit(url).path))


# a TikTok page for one video or photo post, not a signed CDN file
_post_link = is_video_link


def canonical_post(text):
    """
    the one address every reader of a post accepts. yt-dlp only knows
    www.tiktok.com/@x/video/<id>: a link without "www", from m.tiktok.com or
    of a photo post failed with "unsupported url" when the public embed was
    not enough, and a pasted photo post used to mean its whole profile.
    """
    url = _tiktok_url(str(text or ""))
    match = url and _POST_PATH.fullmatch(urlsplit(url).path)
    return f"https://www.tiktok.com/@{match[1]}/video/{match[2]}" if match else text


# ------------------------------------------------------------------ public TikTok access


def _ydl(browser, extra=None):
    # The legacy positional argument is ignored; account sessions are never read.
    from yt_dlp.networking.impersonate import ImpersonateTarget
    o = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        # errors have to come out as exceptions: with ignoreerrors on, a
        # profile that needs a login came back as None, the real reason was
        # lost and the "secondary user id" fallback could never fire
        "ignoreerrors": False,
        "logger": _QuietLogger(),
        "socket_timeout": 30,
        "retries": 3,
        "extractor_retries": 2,
        "impersonate": ImpersonateTarget(client="chrome"),
    }
    if extra:
        o.update(extra)
    # Do not accept authentication options from older integrations.
    o.pop("cookiesfrombrowser", None)
    o.pop("cookiefile", None)
    return yt_dlp.YoutubeDL(o)


def _access_failure(error):
    """Identify public endpoint/challenge failures separately from content errors."""
    text = re.sub(r"\d{6,}", "#", str(error).lower())
    if any(s in text for s in ("private", "rate limit", "429", "not found", "404",
                               "removed", "does not exist")):
        return False
    return any(s in text for s in ("login", "log in", "logged in", "sign in", "403",
                                   "forbidden", "secondary user id", "universal data",
                                   "challenge", "json", "empty response", "answered with nothing",
                                   "blocked public access"))


def _extract_with_access(url, browser, options, download=True):
    """Public embed first, then yt-dlp. Never use a browser account."""
    url = canonical_post(url)
    try:
        info = tiktok_public.video_info(url)
        with _ydl(None, options) as y:
            return y.process_ie_result(info, download=download)
    except (tiktok_public.PublicVideoUnavailable, yt_dlp.utils.DownloadError):
        pass
    try:
        with _ydl(None, options) as y:
            return y.extract_info(url, download=download)
    except Exception as error:
        if _access_failure(error):
            raise TikTokError(_explain_error(str(error))) from error
        raise


def sec_uid_from_video(video_url, browser):
    """derives the profile's internal id from the link of a single video"""
    with _ydl(browser, {"skip_download": True}) as y:
        try:
            info = y.extract_info(video_url, download=False)
        except Exception as e:
            raise TikTokError(_explain_error(str(e)))
    if not info:
        raise TikTokError("cannot read that video")
    sec = info.get("channel_id")
    if not sec:
        raise TikTokError("that video does not expose the profile id")
    return sec, info.get("uploader") or info.get("channel") or None


def _cover(v):
    for t in (v.get("thumbnails") or []):
        if t.get("id") == "cover" and t.get("url"):
            return t["url"]
    for t in (v.get("thumbnails") or []):
        if t.get("url"):
            return t["url"]
    return v.get("thumbnail")


def _entry(v, author):
    # Full video extraction also has a signed CDN 'url'; keep the canonical
    # webpage link so downloads can refresh it and 'Open on TikTok' stays correct.
    u = v.get("webpage_url") or v.get("url")
    if not _post_link(u):
        u = f"https://www.tiktok.com/@{author}/video/{v.get('id')}"
    return {
        "id": str(v.get("id")),
        "url": u,
        "title": (v.get("title") or v.get("description") or "").strip(),
        "duration": v.get("duration"),
        "timestamp": v.get("timestamp"),
        "cover": _cover(v),
        "views": v.get("view_count"),
        "likes": v.get("like_count"),
        "comments": v.get("comment_count"),
    }


def _iter_profile(profile_url, browser, limit=None, video_link=None, log=None):
    """
    a profile's video list AS A STREAM.

    instead of waiting for yt-dlp to finish everything (20 seconds on a
    profile with 575 videos) the videos come out one at a time while tiktok
    is still being paged through: the gallery fills in front of you, and a
    whole-profile run is downloading the first clip two seconds after you
    press the button instead of twenty.

    the first thing yielded is the head of the profile, {"handle", "id"};
    then one dict per video. the trick is process=False: that way entries is
    a real generator and not an already materialised list.
    """
    extra = {"extract_flat": "in_playlist", "skip_download": True}
    limit = positive_limit(limit)
    if limit:
        extra["playlistend"] = limit

    with _ydl(browser, extra) as y:
        name = None
        try:
            # A pasted video is one video, not an implicit request for its account.
            if video_link:
                info = _extract_with_access(video_link, browser, extra, download=False)
            else:
                target = profile_url
                if not profile_url.startswith("tiktokuser:"):
                    try:
                        profile = tiktok_public.profile_info(profile_url)
                    except tiktok_public.PublicVideoUnavailable:
                        pass
                    else:
                        name = profile["handle"]
                        target = "tiktokuser:" + profile["id"]
                info = y.extract_info(target, download=False, process=False)
        except Exception as e:
            text = str(e)
            # tiktok sometimes hides the profile's internal id. if the user
            # pasted the link of a video, it can be pulled out of that
            if "secondary user id" in text.lower() and video_link:
                sec, name = sec_uid_from_video(video_link, browser)
                if log:
                    log(f"tiktok hid the profile id, read it off the video instead ({name or sec[:12]})")
                try:
                    info = y.extract_info(f"tiktokuser:{sec}", download=False, process=False)
                except Exception as e2:
                    raise TikTokError(_explain_error(str(e2)))
            else:
                raise TikTokError(_explain_error(text))
        if not info:
            raise TikTokError(PUBLIC_UNAVAILABLE)

        # the profile's playlist is titled with the user name, its id is the
        # internal one. a tiktokuser: link has no user name: then the one read
        # off the video wins over an unreadable MS4wLjABAAAA... folder name
        author = (name or info.get("uploader") or info.get("title")
                  or info.get("id") or "user")
        yield {"handle": author, "id": info.get("id")}

        entries = info.get("entries")
        if entries is None:
            entries = [info]  # it was the link of a single video

        count, it = 0, iter(entries)
        while True:
            try:
                v = next(it)
            except StopIteration:
                break
            except DownloadCancelled:
                raise
            except Exception as e:
                # tiktok paged us out halfway (rate limit, session gone):
                # keep what came in instead of throwing it all away
                if not count:
                    raise TikTokError(_explain_error(str(e)))
                if log:
                    log(f"tiktok stopped answering after {count} videos: "
                        f"{_explain_error(str(e))}", "warn")
                break
            if not v or not v.get("id"):
                continue
            yield _entry(v, author)
            count += 1
            if limit and count >= limit:
                break


def positive_limit(value):
    """how many videos to take: a whole number above zero, otherwise all of them"""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def iter_profile(profile_url, browser=None, limit=None, video_link=None, log=None):
    """Resolve the first lazy page, then stream without restarting or duplicates."""
    stream = _iter_profile(profile_url, None, limit, video_link, log)
    try:
        head = next(stream)
        first = next(stream, None)
        yield head
        if first is not None:
            yield first
        yield from stream
    finally:
        stream.close()


def explore_stream(profile_url, browser, limit=None, on_head=None,
                   on_batch=None, stopped=None, batch=24, video_link=None):
    """the gallery's view of iter_profile: the videos in small batches"""
    stream = iter_profile(profile_url, browser, limit=limit, video_link=video_link)
    head = next(stream)
    if on_head:
        on_head(head)
    group, total = [], 0
    try:
        for v in stream:
            if stopped and stopped():
                break
            group.append(v)
            total += 1
            if len(group) >= batch:
                if on_batch:
                    on_batch(group, total)
                group = []
    finally:
        stream.close()
    if group and on_batch:
        on_batch(group, total)
    return {"handle": head["handle"], "total": total}


# scraps yt-dlp leaves around while it works, or when an attempt goes wrong:
# they are not videos, and handing one to whisper means failing for no
# understandable reason
_LEFTOVERS = (".part", ".ytdl", ".temp", ".tmp", ".part-frag", ".partial")


def _is_leftover(name):
    n = name.lower()
    return n.endswith(_LEFTOVERS) or ".part-frag" in n


def _sweep_leftovers(folder, prefix):
    """an interrupted download leaves its .part behind: do not keep it"""
    try:
        for f in os.listdir(folder):
            if f.startswith(prefix) and _is_leftover(f):
                try:
                    os.remove(os.path.join(folder, f))
                except OSError:
                    pass
    except OSError:
        pass


def _progress_hook(on_progress, cancelled=None):
    """
    turns yt-dlp's thousand callbacks into a handful of events.

    yt-dlp calls the hook for every block it reads. filtering on whole
    percentage points still left three hundred events per video with three
    parallel downloads, and each one crosses the python->javascript boundary.
    now at most one every 150 ms per video, plus the last one: the eye cannot
    tell the difference, the window can.

    it is also the only place where a download can be stopped halfway: the
    hook raising is what makes yt-dlp let go.
    """
    if not on_progress and not cancelled:
        return []
    state = {"pct": -1, "when": 0.0}

    def hook(d):
        if cancelled and cancelled():
            raise Cancelled("cancelled")
        if not on_progress or d.get("status") != "downloading":
            return
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        if not total:
            return
        pct = min(100, int(d.get("downloaded_bytes", 0) * 100 / total))
        now = time.monotonic()
        if pct == state["pct"]:
            return
        if pct < 100 and now - state["when"] < 0.15:
            return
        state["pct"], state["when"] = pct, now
        on_progress(pct)

    return [hook]


def download_full_video(url, folder, browser, on_progress=None, cancelled=None):
    """
    downloads the video in good quality (not the lightest rendition used for
    transcription): this is the file the user keeps.
    """
    os.makedirs(folder, exist_ok=True)
    expected = (re.search(r"/video/(\d+)", canonical_post(url) or "") or [None, None])[1]
    opts = {
        "format": FULL_FORMAT,
        "outtmpl": os.path.join(folder, "%(id)s - %(title).60s.%(ext)s"),
        "noplaylist": True,
        "restrictfilenames": False,
        "windowsfilenames": True,
        "progress_hooks": _progress_hook(on_progress, cancelled),
    }
    try:
        info = _extract_with_access(url, browser, opts)
    except BaseException:
        if expected:
            _sweep_leftovers(folder, expected)
        raise
    if not info:
        raise TikTokError("download failed")
    expected = str(info.get("id"))
    for f in sorted(os.listdir(folder)):
        if f.startswith(expected) and not _is_leftover(f):
            return os.path.join(folder, f)
    raise TikTokError("file not found after the download")


def download_clip(video, folder, browser, on_progress=None, cancelled=None):
    """downloads the lightest rendition of the video, returns its path"""
    opts = {
        "format": CLIP_FORMAT,
        "outtmpl": os.path.join(folder, f"{video['id']}.%(ext)s"),
        "noplaylist": True,
        "progress_hooks": _progress_hook(on_progress, cancelled),
    }
    info = _extract_with_access(video["url"], browser, opts)
    if not info:
        raise TikTokError("download failed")
    path = None
    # sorted and without the leftovers: os.listdir promises no order, and a
    # ".part" left behind by a failed attempt matches just like the real video
    for f in sorted(os.listdir(folder)):
        if f.startswith(video["id"] + ".") and not _is_leftover(f):
            path = os.path.join(folder, f)
            break
    if not path or not os.path.exists(path):
        raise TikTokError("file not found after the download")
    return path, info


def transcribe_one(video, folder, browser, engine, options, on_state=None,
                   cancelled=None):
    """
    a single video, with the whisper engine ALREADY loaded from the outside.

    the gallery needs this: reloading the model on every click would cost ten
    seconds per video, and on a single click you feel every one of them.
    returns the row describing what it wrote.
    """
    def state(s, **extra):
        if on_state:
            on_state(s, **extra)

    def check():
        if cancelled and cancelled():
            raise Cancelled("cancelled")

    os.makedirs(folder, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="tks_")
    try:
        state("downloading", pct=0)
        path, info = download_clip(
            video, tmp, browser,
            on_progress=lambda p: state("downloading", pct=p),
            cancelled=cancelled,
        )
        check()
        state("transcribing")
        language = options.get("language") or "auto"
        lines, meta = transcribe_audio(engine, path, None if language == "auto" else language, cancelled)
        lines, suspect = _strip_repeats(lines)
        check()
        row = write_transcript(folder, video, info, lines, meta,
                               options.get("format", "md"), bool(options.get("timestamps")),
                               options.get("ui_language", "en"))
        state("done", file=row["path"], words=row["words"], language=row["language"],
              suspect=suspect)
        return row
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _explain_error(text):
    """
    turns a yt-dlp message into something a human can act on.

    the comparisons are ANCHORED on purpose. searching for "404" anywhere in
    the text meant hitting it inside a video id (19 digits: it happens), and
    a plain network error turned into "no such profile". same story with
    "private", which also matched "private video is not available" — the
    video, not the profile — and with "login", which is inside half the world.
    """
    if text == PUBLIC_UNAVAILABLE:
        return text
    t = (text or "").lower()
    # strip long numbers (video ids, profile ids): any three-digit run you can
    # think of lives inside them, 404 included
    clean = re.sub(r"\d{6,}", "#", t)

    def has(*phrases):
        return any(p in clean for p in phrases)

    if has("account is private", "private account", "profile is private",
           "user's account is private"):
        return "private profile, nothing to be done"
    if has("does not have any videos"):
        return "the profile has no videos"
    if has("requiring login", "requires login", "log in", "sign in", "login required",
           "log into"):
        return (
            "This content is not publicly available."
        )
    if has("secondary user id"):
        return (
            "tiktok will not give me the profile id. try pasting the link of a single "
            "video from that profile instead of the profile link."
        )
    if has("video is private", "post is private", "private video"):
        return "this video is private"
    if has("http error 403", " 403:", "error 403", "forbidden"):
        return (
            "TikTok is not responding. Try again in a few minutes."
        )
    if has("unable to find", "user not found", "profile not found",
           "does not exist", "http error 404", " 404:", "error 404"):
        return "no such profile, check how you spelled it"
    if has("video not found", "removed by", "has been removed"):
        return "the video is gone"
    if has("no video formats", "requested format is not available"):
        return "tiktok offers no playable video here (a photo post, maybe)"
    if re.search(r"rate.{0,12}limit|too many requests|http error 429", clean):
        return "tiktok is rate limiting you. wait ten minutes or so and try again."
    if has("failed to parse json", "expecting value"):
        return PUBLIC_UNAVAILABLE
    if has("timed out", "timeout", "connection reset", "connection aborted",
           "temporary failure in name resolution", "getaddrinfo failed"):
        return "the network did not answer. try again."
    # what is left is yt-dlp's own sentence: without its "ERROR: [TikTok]
    # 7107337212743830830:" in front, which says nothing to anybody
    text = re.sub(r"^error:\s*(\[[^\]]+\]\s*)?([\w.@-]+:\s+)?", "", (text or "").strip(),
                  flags=re.I)
    return (text or "unknown error").split("\n")[0][:220]


# ------------------------------------------------------------------ whisper


def whisper_installed():
    try:
        import faster_whisper  # noqa: F401

        return True
    except Exception:
        return False


def models_cache_dir():
    """where huggingface keeps the models (HF_HOME and friends respected)"""
    try:
        from huggingface_hub import constants

        return constants.HF_HUB_CACHE
    except Exception:
        return os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")


def _model_folder(name):
    repo = MODELS[model_name(name)]["repo"]
    return os.path.join(models_cache_dir(), "models--" + repo.replace("/", "--"))


def _model_snapshot(name):
    name = model_name(name)
    return os.path.join(_model_folder(name), "snapshots", MODELS[name]["revision"])


def natural_model_files():
    """Pinned local ASR and language-ID files; never resolve a moving branch."""
    return [os.path.join(models_cache_dir(), "models--" + m["repo"].replace("/", "--"),
                         "snapshots", m["revision"], m["filename"])
            for m in (MODELS["qwen3-asr"], LANGUAGE_MODEL)]


def model_downloaded(name=DEFAULT_MODEL):
    """Only a complete, tested snapshot is ready for fully local inference."""
    name = model_name(name)
    if name == "qwen3-asr":
        try:
            return all(os.path.getsize(path) == m["bytes"] for path, m in
                       zip(natural_model_files(), (MODELS[name], LANGUAGE_MODEL)))
        except OSError:
            return False
    folder = _model_snapshot(name)
    required = ["model.bin", "config.json", "tokenizer.json"]
    try:
        return (all(os.path.getsize(os.path.join(folder, f)) > 0 for f in required)
                and any(os.path.isfile(os.path.join(folder, f))
                        and os.path.getsize(os.path.join(folder, f)) > 0
                        for f in ("vocabulary.json", "vocabulary.txt")))
    except OSError:
        return False


def model_size_on_disk(name):
    size = 0
    folders = [_model_folder(name)]
    if name == "qwen3-asr":
        folders.append(os.path.join(models_cache_dir(), "models--" + LANGUAGE_MODEL["repo"].replace("/", "--")))
    for folder in folders:
        for root, _, files in os.walk(folder):
            for f in files:
                try:
                    size += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    return size


def gpu_available(name=None):
    """
    returns (usable, description). it is not enough for ctranslate2 to see the
    card: without the cublas dlls the model loads and then dies on the first
    inference, so the engine also does a dry run when it loads.
    """
    if name == "qwen3-asr":
        # apple computers run it on Metal, everything else on Vulkan
        backend, label = ("metal", "Metal") if desktop.MAC else ("vulkan", "Vulkan")
        try:
            import transcribe_cpp
            available = transcribe_cpp.backend_available(backend)
            return available, label if available else "processor"
        except Exception:
            return False, "processor"
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() < 1:
            return False, "no nvidia card found"
        if "float16" not in ctranslate2.get_supported_compute_types("cuda"):
            return False, "the card cannot handle float16"
    except Exception as e:
        return False, f"ctranslate2 does not see the gpu: {type(e).__name__}"
    if not CUDA_DLLS:
        return False, "the cuda libraries are missing (nvidia-cublas-cu12, nvidia-cudnn-cu12)"
    return True, "gpu ready"


# ------------------------------------------------------------ getting ready
#
# the first start has two big things to fetch: the whisper model, and on a
# pc with an nvidia card the two cuda libraries ctranslate2 needs. the
# program fetches both by itself and says how far along it is: there is no
# installer any more that could do it, or fail at it.

# who to tell about it: the app puts a function in here
setup_listener = None
_setup_lock = threading.Lock()

# the two libraries, straight from the official nvidia packages on pypi.
# cudnn has to be 9 (ctranslate2 4 is built against it), cublas the cuda 12 one
CUDA_PACKAGES = (("nvidia-cublas-cu12", None), ("nvidia-cudnn-cu12", "9"))


def _setup(stage, text, pct=None, done=False, error=None):
    if setup_listener:
        try:
            setup_listener({"stage": stage, "text": text, "pct": pct, "done": done, "error": error})
        except Exception:
            pass


def nvidia_card():
    """an nvidia card the cuda runtime can see, libraries or not"""
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def _gb(n):
    return f"{n / 1e9:.1f} gb"


def _version_key(v):
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.+]", v))


def _wheel(package, major=None):
    """the newest stable wheel of a package for this computer: (url, size, version)"""
    import json
    import platform
    import urllib.request

    if desktop.WINDOWS:
        fits = lambda name: name.endswith("win_amd64.whl")
    else:
        machine = {"amd64": "x86_64", "arm64": "aarch64"}.get(platform.machine().lower(),
                                                              platform.machine().lower())
        fits = lambda name: "manylinux" in name and name.endswith(machine + ".whl")
    with urllib.request.urlopen(f"https://pypi.org/pypi/{package}/json", timeout=30) as r:
        data = json.load(r)
    for version in sorted(data["releases"], key=_version_key, reverse=True):
        if re.search(r"[a-z]", version) or (major and not version.startswith(major + ".")):
            continue
        for f in data["releases"][version]:
            if fits(f["filename"]) and not f.get("yanked"):
                return f["url"], f["size"], version
    if desktop.WINDOWS:
        raise TikTokError(f"no windows build of {package} on pypi")
    raise TikTokError(f"no linux build of {package} on pypi")


def install_cuda():
    """
    downloads the cuda libraries into CUDA_DIR and puts them on the search
    path. only the .dll files are kept out of each package.
    """
    import urllib.request
    import zipfile

    global CUDA_DLLS
    wheels = [(p,) + _wheel(p, major) for p, major in CUDA_PACKAGES]
    total = sum(w[2] for w in wheels)
    done = 0
    os.makedirs(CUDA_DIR, exist_ok=True)
    for package, url, size, version in wheels:
        part = os.path.join(CUDA_DIR, package + ".whl.partial")
        with urllib.request.urlopen(url, timeout=60) as r, open(part, "wb") as f:
            last = 0.0
            while True:
                block = r.read(1 << 20)
                if not block:
                    break
                f.write(block)
                done += len(block)
                if time.monotonic() - last > 0.5:
                    last = time.monotonic()
                    _setup("cuda", f"Downloading the graphics card libraries · {_gb(done)} of {_gb(total)}",
                           done / total)
        _setup("cuda", "Unpacking the graphics card libraries", done / total)
        keep = (r"nvidia/[^/]+/bin/[^/]+\.dll" if desktop.WINDOWS
                else r"nvidia/[^/]+/lib/lib[^/]+\.so[.0-9]*")
        with zipfile.ZipFile(part) as z:
            for member in z.namelist():
                if re.fullmatch(keep, member):
                    target = os.path.join(CUDA_DIR, *member.split("/"))
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with z.open(member) as src, open(target + ".partial", "wb") as dst:
                        shutil.copyfileobj(src, dst, 1 << 20)
                    os.replace(target + ".partial", target)
        os.remove(part)
    CUDA_DLLS = _hook_cuda()
    return CUDA_DLLS


def download_model(name=DEFAULT_MODEL):
    """
    the model, with its progress: faster-whisper's own download says nothing
    while it fetches 1.6 gb, so the files are watched growing in the cache.
    """
    from faster_whisper.utils import download_model as fetch

    name = model_name(name)
    total = int(float(MODELS[name]["size"].split()[0]) * 1e9)
    folder = _model_folder(name)
    stop = threading.Event()

    def watch():
        while not stop.wait(0.5):
            have = 0
            folders = [folder]
            if name == "qwen3-asr":
                folders.append(os.path.join(models_cache_dir(), "models--" + LANGUAGE_MODEL["repo"].replace("/", "--")))
            for source in folders:
                for f in glob.glob(os.path.join(source, "blobs", "*")):
                    try:
                        have += os.path.getsize(f)
                    except OSError:
                        pass
            _setup("model", f"Downloading the transcription model · {_gb(min(have, total))} of {_gb(total)}",
                   min(0.99, have / total))

    threading.Thread(target=watch, daemon=True).start()
    try:
        if name == "qwen3-asr":
            from huggingface_hub import hf_hub_download
            for path, model in zip(natural_model_files(), (MODELS[name], LANGUAGE_MODEL)):
                kwargs = {"revision": model["revision"], "token": False}
                if os.path.isfile(path) and os.path.getsize(path) != model["bytes"]:
                    kwargs["force_download"] = True
                hf_hub_download(model["repo"], model["filename"], **kwargs)
        else:
            fetch(MODELS[name]["repo"], revision=MODELS[name]["revision"], use_auth_token=False)
    finally:
        stop.set()


def ensure_ready(name=DEFAULT_MODEL, log=None):
    """
    everything a transcription needs, fetched if it is missing. safe to call
    from several places at once: the second caller waits for the first.
    a broken cuda download is not fatal, whisper falls back to the processor.
    """
    name = model_name(name)
    with _setup_lock:
        if name != "qwen3-asr" and not desktop.MAC and not CUDA_DLLS and nvidia_card():
            if log:
                log("nvidia card found: fetching its libraries (about 1.2 gb, only the first time)")
            try:
                install_cuda()
                _setup("cuda", "Graphics card ready", 1, done=True)
            except Exception as e:
                _setup("cuda", "The graphics card libraries did not download", None, done=True,
                       error=f"{_explain_error(str(e))}. Whisper uses the processor for now.")
                if log:
                    log(f"the cuda libraries did not download ({e}): using the cpu", "warn")
        if not model_downloaded(name):
            if log:
                log(f"downloading the '{name}' model ({MODELS[name]['size']}). only the first time.")
            try:
                download_model(name)
            except Exception as e:
                _setup("model", "The transcription model did not download", None, done=True,
                       error=_explain_error(str(e)))
                raise
            _setup("model", "Transcription model ready", 1, done=True)


# lines whisper writes over music or silence because it learned them from
# subtitle files: they are never somebody speaking, so they go
_CREDITS = re.compile(
    r"amara\.org|subtitles? (by|created by|provided by)|sottotitoli (creati|a cura|di)|"
    r"untertitel (der|im auftrag|von)|sous-titr|subt\wtulos (realizados|por)|"
    r"transcribed by",
    re.I,
)


class Engine:
    """Keep the chosen local model loaded once for the whole job."""

    def __init__(self, name=DEFAULT_MODEL, log=print):
        self.name = name = model_name(name)
        ensure_ready(name, log)
        if name == "qwen3-asr":
            from natural_asr import NaturalEngine
            t0 = time.time()
            self._natural = NaturalEngine(*natural_model_files(), log=log)
            self.workers = self._natural.workers
            self.device, self.compute = self._natural.device, self._natural.compute
            log(f"model ready in {time.time() - t0:.1f}s on {self.device}, 1 transcriptions in parallel", "ok")
            return
        from faster_whisper import WhisperModel
        ok, why = gpu_available()
        if ok:
            self.device, self.compute = "cuda", "float16"
            self.workers = GPU_TRANSCRIBERS
        else:
            self.device, self.compute = "cpu", "int8"
            self.workers = TRANSCRIBERS
            log(f"no gpu ({why}): falling back to the cpu, it will be slow.", "warn")

        log(f"loading '{name}' on {self.device} ({self.compute})...")
        t0 = time.time()
        try:
            self.m = WhisperModel(
                _model_snapshot(name), device=self.device, compute_type=self.compute,
                cpu_threads=THREADS_EACH if self.device == "cpu" else 0,
                num_workers=self.workers,
            )
            self._smoke_test()
        except Exception as e:
            if self.device != "cuda":
                raise
            log(f"the gpu refused ({str(e)[:110]}). falling back to the cpu.", "warn")
            self.device, self.compute, self.workers = "cpu", "int8", TRANSCRIBERS
            self.m = WhisperModel(
                _model_snapshot(name), device="cpu", compute_type="int8",
                cpu_threads=THREADS_EACH, num_workers=TRANSCRIBERS,
            )
        log(
            f"model ready in {time.time() - t0:.1f}s on {self.device}, "
            f"{self.workers} transcriptions in parallel",
            "ok",
        )

    def _smoke_test(self):
        """
        one dry run on three seconds of silence. needed because with cuda the
        model loads beautifully and then blows up on the FIRST real inference
        when the dlls are missing: better to find out now than halfway
        through 200 videos.
        """
        import numpy as np

        segments, _ = self.m.transcribe(
            np.zeros(16000 * 3, dtype=np.float32), language="en", beam_size=1
        )
        list(segments)

    def transcribe(self, path, language=None, cancelled=None):
        if getattr(self, "_natural", None) is not None:
            result = self._natural.transcribe(path, language)
            self.device = self._natural.device
            return result
        segments, info = self.m.transcribe(
            path,
            language=None if language in (None, "auto") else language,
            beam_size=5,
            vad_filter=True,
            # Reject isolated sub-100 ms transients before padding: an ASMR
            # packaging click previously became a 0.9 s "speech" region after
            # padding, which Whisper rendered as a made-up closing sentence.
            vad_parameters={"min_silence_duration_ms": 300, "min_speech_duration_ms": 100},
            # the three lines below fight whisper's hallucinations on videos
            # with no speech, where it otherwise invents whole sentences
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
        )
        lines = []
        for s in segments:
            # whisper works one segment at a time as they are read: a stop or
            # a cancelled gallery card no longer waits for the whole video
            if cancelled and cancelled():
                raise Cancelled("cancelled")
            text = re.sub(r"\s+", " ", s.text).strip()
            if not text or _CREDITS.search(text):
                continue
            lines.append({"start": s.start, "end": s.end, "text": text})
        return lines, {
            # Silence has no spoken language; VAD may otherwise return an
            # arbitrary default with probability 1. This is language confidence,
            # never a measure of how many transcript words are correct.
            "language": info.language if lines else "",
            "confidence": (round(info.language_probability or 0, 2) if language in (None, "auto")
                           else None) if lines else 0,
        }


    def transcribe_cancellable(self, path, language=None, cancelled=None):
        if getattr(self, "_natural", None) is not None:
            from natural_asr import TranscriptionCancelled
            try:
                result = self._natural.transcribe(path, language, cancelled)
                self.device = self._natural.device
                return result
            except TranscriptionCancelled:
                raise Cancelled("cancelled") from None
        return self.transcribe(path, language, cancelled)


def transcribe_audio(engine, path, language=None, cancelled=None):
    method = getattr(engine, "transcribe_cancellable", None)
    return method(path, language, cancelled) if method else engine.transcribe(path, language)


def _strip_repeats(lines):
    """
    on videos with no speech whisper repeats the same sentence forever.
    if more than half the lines are identical, the result is worthless.
    """
    if len(lines) < 4:
        return lines, False
    texts = [r["text"].lower() for r in lines]
    most_common = max(set(texts), key=texts.count)
    if texts.count(most_common) / len(texts) > 0.5:
        return lines[:1], True
    out = []
    for r in lines:
        if out and out[-1]["text"].lower() == r["text"].lower():
            continue
        out.append(r)
    return out, False


# ------------------------------------------------------------------ output


def _date(ts):
    return time.strftime("%Y-%m-%d", time.localtime(ts)) if ts else ""


def _stamp(seconds):
    seconds = int(seconds)
    if seconds >= 3600:
        return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
    return f"{seconds // 60}:{seconds % 60:02d}"


def _readable_groups(lines):
    """Group the recognizer's exact words into paragraphs, without rewriting.

    A segment is an audio alignment unit, not necessarily a sentence. Prefer
    existing sentence endings; use a substantial audio pause for unpunctuated
    speech. Do not invent full stops, capitals, headings or missing words.
    """
    paragraphs, group, current = [], [], ""
    previous_end = None
    for index, row in enumerate(lines):
        text = re.sub(r"\s+", " ", row["text"]).strip()
        if not text:
            continue
        start, end = row.get("start"), row.get("end")
        gap = start - previous_end if start is not None and previous_end is not None else 0
        if current and len(current) >= 160 and gap >= 1.0:
            paragraphs.append(group)
            group, current = [], ""
        # Splitting at whitespace leaves decimal points, URLs and initials
        # intact. A mistaken abbreviation boundary can only affect whitespace.
        sentences = re.split(r'(?<=[.!?。！？])\s+(?=\S)', text)
        for sentence in sentences:
            if (current and len(current) >= 280
                    and re.search(r'[.!?。！？][\"\u201d\u2019)\]]?$', current)):
                paragraphs.append(group)
                group, current = [], ""
            if group and group[-1]["_source"] == index:
                group[-1]["text"] += " " + sentence
            else:
                group.append({**row, "text": sentence, "_source": index})
            current = (current + " " + sentence).strip()
        previous_end = end
    if current:
        paragraphs.append(group)
    return paragraphs


def readable_text(lines):
    return "\n\n".join(" ".join(r["text"] for r in group) for group in _readable_groups(lines))


def compose(video, info, lines, meta, fmt="md", timestamps=False, ui_language="en"):
    from localization import translate
    tr = lambda key, **params: translate(key, ui_language, **params)
    title = one_line(video.get("title") or info.get("title") or tr("untitled"))
    handle = info.get("uploader") or info.get("channel") or video.get("handle") or ""
    duration = info.get("duration") or video.get("duration")
    url = info.get("webpage_url") or video.get("url")
    date = _date(info.get("timestamp") or video.get("timestamp"))

    body = readable_text(lines) or tr("(no speech)")
    words = len(body.split()) if lines else 0
    language_info = meta.get("language") or "?"
    if meta.get("language") and meta.get("confidence") is not None:
        language_info += f" ({tr('confidence')} {meta['confidence']})"

    if fmt == "md":
        out = [f"# {title[:120]}", ""]
        if handle:
            out.append(f"- {tr('profile')}: @{handle}")
        if date:
            out.append(f"- {tr('date')}: {date}")
        if duration:
            out.append(f"- {tr('duration')}: {int(duration)}s")
        out.append(f"- {tr('language')}: {language_info}")
        out.append(f"- {tr('words')}: {words}")
        if url:
            out.append(f"- {tr('link')}: {url}")
        out += ["", "---", ""]
        if timestamps and lines:
            for group in _readable_groups(lines):
                for r in group:
                    out.append(f"**[{_stamp(r['start'])}]** {r['text']}  ")
                out.append("")
        else:
            out.append(body)
        return "\n".join(out).rstrip() + "\n"

    out = [title[:120]]
    if handle:
        out.append(f"@{handle}")
    # Plain text must retain metadata too: gallery collections are rebuilt from
    # disk, without the in-memory Whisper result. Previously .txt lost language
    # and duration in the CSV, unlike Markdown.
    if date:
        out.append(f"- {tr('date')}: {date}")
    if duration:
        out.append(f"- {tr('duration')}: {int(duration)}s")
    out.append(f"- {tr('language')}: {language_info}")
    out.append(f"- {tr('words')}: {words}")
    if url:
        out.append(url)
    out += ["-" * 60, ""]
    if timestamps and lines:
        for group in _readable_groups(lines):
            for r in group:
                out.append(f"[{_stamp(r['start'])}] {r['text']}")
            out.append("")
    else:
        out.append(body)
    return "\n".join(out).rstrip() + "\n"


def transcripts_on_disk(folder):
    """id -> path of every transcript in a profile folder"""
    out = {}
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return out
    for f in names:
        m = TRANSCRIPT_RE.match(f)
        if m and os.path.isfile(os.path.join(folder, f)):
            out[m.group(1)] = os.path.join(folder, f)
    return out


def write_transcript(folder, video, info, lines, meta, fmt="md", timestamps=False, ui_language="en"):
    """
    writes one transcript and returns the row that describes it.

    any other file for the same video goes: a redo with another format, or a
    caption edited on tiktok since the last time, used to leave two
    transcripts of one video, and both ended up in the collection.
    """
    text = compose(video, info, lines, meta, fmt, timestamps, ui_language)
    title = safe_name(video.get("title") or info.get("title") or video["id"])
    name = f"{video['id']} - {title}.{fmt}"
    path = os.path.join(folder, name)
    _atomic_write(path, text)
    for f in os.listdir(folder):
        m = TRANSCRIPT_RE.match(f)
        if m and m.group(1) == video["id"] and f != name:
            try:
                os.remove(os.path.join(folder, f))
            except OSError:
                pass
    spoken = readable_text(lines)
    return {
        "id": video["id"],
        "title": one_line(video.get("title") or info.get("title") or ""),
        "url": info.get("webpage_url") or video.get("url") or "",
        "duration": info.get("duration") or video.get("duration"),
        "date": _date(info.get("timestamp") or video.get("timestamp")),
        "language": meta.get("language") or "",
        "words": len(spoken.split()),
        "text": spoken,
        "file": name,
        "path": path,
    }


# "**[1:23]** " in markdown, "[1:23] " in text: the times, when they are on
_LINE_STAMP = re.compile(r"^(\*\*)?\[\d+(:\d{2}){1,2}\](\*\*)?\s*")


def _read_transcript(path):
    """
    reads back a transcript this program wrote: the header as a dict, the
    spoken text with its paragraph boundaries preserved.
    """
    from localization import metadata_labels, silence_labels
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    head, body = lines, []
    for i, line in enumerate(lines):
        s = line.strip()
        if s == "---" or (len(s) >= 20 and set(s) == {"-"}):
            head, body = lines[:i], lines[i + 1:]
            break
    meta = {}
    if head:
        title = head[0]
        if str(path).lower().endswith(".md") and title.startswith("# "):
            title = title[2:]
        meta["title"] = title.strip()
    for line in head[1:]:
        m = re.match(r"^- ([^:]+): (.*)$", line.strip())
        if m and m[1] in metadata_labels():
            key, value = metadata_labels()[m[1]], m[2]
            if key == "duration":
                value = value.rstrip("s")
            elif key == "language":
                value = value.split(" ")[0]
                if value == "?":
                    value = ""
            meta["url" if key == "link" else key] = value
        elif line.startswith("http"):
            meta["url"] = line.strip()
        elif re.search(r"\| \d{4}-\d{2}-\d{2}$", line.strip()):
            # the .txt header: "@someone | 2026-08-04"
            meta["date"] = line.strip()[-10:]
    # Keep paragraph boundaries, including those chosen from audio pauses in a
    # timestamped export. Legacy MD with a blank after every segment retains
    # those explicit boundaries too. Hard-wrapped lines remain in one paragraph.
    paragraphs, current = [], []
    for line in body + [""]:
        cleaned = _LINE_STAMP.sub("", line.strip())
        if cleaned:
            current.append(cleaned)
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    text = "\n\n".join(paragraphs)
    return meta, "" if text in silence_labels() else text


def rebuild_collection(folder, handle, fresh=(), ui_language="en"):
    """
    the two summary files, rebuilt from EVERY transcript in the folder.

    they used to be written from the current run only: resume a profile where
    150 videos were already done, transcribe the 10 new ones, and the "all in
    one" file came out with 10 videos in it. the transcripts made from the
    gallery never got in at all.

    the metadata comes, best first, from the run that just finished, from the
    csv of the previous runs, from the transcript's own header.
    """
    from localization import translate
    tr = lambda key, **params: translate(key, ui_language, **params)
    handle = str(handle).lstrip("@")
    on_disk = transcripts_on_disk(folder)
    if not on_disk:
        return 0
    csv_path = os.path.join(folder, f"_index @{handle}.csv")
    known = {}
    try:
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f, delimiter=";"):
                if r.get("id"):
                    known[r["id"]] = r
    except (OSError, csv.Error):
        pass
    fresh = {r["id"]: r for r in fresh}

    rows = []
    for vid, path in on_disk.items():
        try:
            header, text = _read_transcript(path)
        except OSError:
            continue
        old = known.get(vid, {})
        new = fresh.get(vid, {})

        def pick(key, csv_key=None):
            # A gallery redo can change language/title/duration. The file on
            # disk is newer than the previous index. Legacy sparse .txt headers
            # still fall back to that index for fields they did not contain.
            if key in new:
                return new[key]
            if key in header:
                return header[key]
            return old.get(csv_key or key) or ""

        duration = pick("duration", "duration_s")
        try:
            duration = int(float(duration))
        except (TypeError, ValueError):
            duration = 0
        rows.append({
            "id": vid,
            "date": pick("date"),
            "duration": duration,
            "language": pick("language"),
            "title": one_line(pick("title")),
            "url": pick("url") or f"https://www.tiktok.com/@{handle}/video/{vid}",
            "file": os.path.basename(path),
            "text": text,
            "words": len(text.split()),
        })
    # tiktok ids grow with time: newest first, the way the profile shows them
    rows.sort(key=lambda r: int(r["id"]), reverse=True)

    head = [
        "# " + tr("every transcript of @{p0}", p0=handle),
        "",
        f"- {tr('videos transcribed')}: {len(rows)}",
        f"- {tr('total words')}: {sum(r['words'] for r in rows)}",
        f"- {tr('generated on')}: {time.strftime('%Y-%m-%d %H:%M')}",
        "",
        "---",
        "",
    ]
    body = []
    for r in rows:
        body.append(f"## {(r['title'] or r['id'])[:110]}")
        body.append("")
        facts = [x for x in (r["date"], f"{r['duration']}s" if r["duration"] else "", r["url"]) if x]
        body.append(" · ".join(facts))
        body.append("")
        body.append(r["text"] or tr("(no speech)"))
        body.append("")
    _atomic_write(os.path.join(folder, f"_ALL @{handle}.md"),
                  "\n".join(head + body).rstrip() + "\n")

    import io

    buffer = io.StringIO()
    w = csv.writer(buffer, delimiter=";")
    w.writerow(["id", "date", "duration_s", "language", "words", "title", "url", "file"])
    for r in rows:
        w.writerow([r["id"], r["date"], r["duration"], r["language"], r["words"],
                    r["title"][:200], r["url"], r["file"]])
    _atomic_write(csv_path, buffer.getvalue(), encoding="utf-8-sig", newline="")
    return len(rows)


def profile_folder(base, handle):
    return os.path.join(base, safe_name("@" + str(handle).lstrip("@")))


def clean_temp(max_age=6 * 3600):
    """
    the clips download into the temp folder and get deleted as they are done.
    a window closed in the middle of a run cannot do that: the next start
    sweeps up whatever an earlier one left behind.
    """
    base = tempfile.gettempdir()
    now = time.time()
    for d in glob.glob(os.path.join(base, "tk[sx]_*")):
        try:
            if now - os.path.getmtime(d) > max_age:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


# ------------------------------------------------------------------ the job


class Transcriber:
    """
    runs the whole thing. the list streams in, four threads download, the
    rest transcribe, so the network and the gpu work together instead of
    waiting for each other.
    """

    def __init__(self, options, emit, engine=None):
        """
        `engine` is a callable(log) that returns a loaded Engine. the app
        passes its own, so a run reuses the model the gallery already loaded
        instead of putting a second copy of it in the graphics memory.
        """
        self.o = options
        self._emit = emit
        self._engine = engine or (
            lambda log: Engine(options.get("model") or DEFAULT_MODEL, log=log))
        self.stop = threading.Event()
        self.results = {}
        self._lock = threading.Lock()
        self._done = 0
        self._errors = 0
        self._skipped = 0
        self._running = 0        # how many are actually in flight right now
        self._finished_at = deque(maxlen=24)
        self._total = 0
        self._listing = True
        self._fatal = None
        # Auto means detect EACH video, including multilingual profiles. A few
        # initial clips cannot establish the language of the rest of an account.
        self._fixed_language = None

    # ------------------------------------------------------------ events

    def _ev(self, kind, **data):
        try:
            self._emit({"type": kind, **data})
        except Exception:
            pass

    def log(self, text, level="info"):
        self._ev("log", text=str(text), level=level)

    def _video_state(self, vid, state, **extra):
        self._ev("video", id=vid, state=state, **extra)

    def _eta(self, left):
        """
        from the real pace of the last videos finished, not from how long one
        transcription takes: with two or four of them in parallel, and the
        downloads in between, that number was off by a factor of two to four.
        """
        times = self._finished_at
        if len(times) < 3 or not left:
            return None
        span = times[-1] - times[0]
        if span <= 0:
            return None
        return int(left * span / (len(times) - 1))

    def _progress(self):
        # everything read in one go under the lock: otherwise the numbers that
        # end up on the same screen are sampled at different moments and do
        # not add up
        with self._lock:
            ok, errors, skipped = self._done, self._errors, self._skipped
            running = max(0, self._running)
            done = ok + errors + skipped
            left = max(0, self._total - done)
            eta = self._eta(left)
            listing = self._listing
        self._ev(
            "progress",
            done=done,
            ok=ok,
            errors=errors,
            skipped=skipped,
            running=min(running, left),
            queued=max(0, left - running),
            total=self._total,
            listing=listing,
            eta=eta,
        )

    def _check_stop(self):
        if self.stop.is_set():
            if self._fatal:
                raise TikTokError(self._fatal)
            raise Stopped()

    # ------------------------------------------------------------ the run

    def run(self):
        out_folder = None
        try:
            out_folder = self._run()
        except Stopped:
            self.log("stopped by you.", "warn")
        except TikTokError as e:
            self.log(str(e), "err")
        except Exception as e:
            import traceback

            self.log(f"crash: {e}", "err")
            self.log(traceback.format_exc(limit=3), "info")
        finally:
            self._ev(
                "finished",
                ok=self._done,
                errors=self._errors,
                skipped=self._skipped,
                folder=out_folder or getattr(self, "folder", None),
            )

    def _run(self):
        o = self.o
        url, label, video_link = normalize_profile(o["profile"])

        if not whisper_installed():
            raise TikTokError(
                "the transcription engine is missing. run INSTALL.bat again, or:\n"
                "python -m pip install faster-whisper"
            )

        # 1. whisper, in the background: loading it takes about ten seconds,
        #    and they are the same ten seconds tiktok takes to hand over the
        #    first videos
        engine_ready = threading.Event()
        box = {}

        def load():
            try:
                box["engine"] = self._engine(self.log)
            except Exception as e:
                self._fatal = f"the transcription engine did not load: {e}"
                self.stop.set()
            finally:
                engine_ready.set()

        # 2. public access; old saved browser choices are ignored.
        browser = None
        self._check_stop()

        # 3. the list, as a stream
        self.log(f"asking tiktok for the videos of {label}...")
        stream = iter_profile(url, browser, limit=o.get("limit"),
                              video_link=video_link, log=self.log)
        head = next(stream)
        # Do not download gigabytes of models for a link TikTok refused to open.
        threading.Thread(target=load, daemon=True, name="engine-load").start()
        handle = head["handle"]
        self._ev("profile", handle=handle, total=None, label=label)

        base = o.get("folder") or default_output_folder()
        self.folder = folder = profile_folder(base, handle)
        os.makedirs(folder, exist_ok=True)

        # resume from where it left off: if the file is already there, redo nothing
        already_done = set(transcripts_on_disk(folder)) if o.get("resume", True) else set()
        if already_done:
            self.log(f"{len(already_done)} videos were already there, skipping them", "warn")

        # 4. the assembly line
        tmp = tempfile.mkdtemp(prefix="tkx_")
        work = queue.Queue(maxsize=(DOWNLOADERS + TRANSCRIBERS) * 2)
        fmt = o.get("format", "md")
        language = o.get("language", "auto")
        timestamps = bool(o.get("timestamps", False))
        if language and language != "auto":
            self._fixed_language = language

        def forget(path):
            try:
                os.remove(path)
            except OSError:
                pass

        def downloader(v):
            if self.stop.is_set():
                return
            if v["id"] in already_done:
                with self._lock:
                    self._skipped += 1
                self._video_state(v["id"], "skipped")
                self._progress()
                return
            with self._lock:
                self._running += 1
            self._video_state(v["id"], "downloading", pct=0)
            self._progress()
            try:
                path, info = download_clip(
                    v, tmp, browser,
                    on_progress=lambda p, _id=v["id"]: self._ev("percent", id=_id, pct=p),
                    cancelled=self.stop.is_set,
                )
            except Exception as e:
                with self._lock:
                    self._running -= 1
                    if not self.stop.is_set():
                        self._errors += 1
                        self._finished_at.append(time.monotonic())
                if self.stop.is_set():
                    self._video_state(v["id"], "queued")
                else:
                    self._video_state(v["id"], "error", message=_explain_error(str(e))[:120])
                self._progress()
                return
            # the queue has a ceiling, so the downloads wait for whisper
            # instead of filling the disk. a plain put would wait forever if
            # the run is stopped while nobody is draining it any more
            while True:
                try:
                    work.put((v, path, info), timeout=0.5)
                    return
                except queue.Full:
                    if self.stop.is_set():
                        with self._lock:
                            self._running -= 1
                        forget(path)
                        return

        def transcriber(engine):
            while True:
                item = work.get()
                try:
                    if item is None:
                        return
                    v, path, info = item
                    if self.stop.is_set():
                        with self._lock:
                            self._running -= 1
                        forget(path)
                        continue
                    self._video_state(v["id"], "transcribing")
                    try:
                        with self._lock:
                            chosen = self._fixed_language
                        lines, meta = transcribe_audio(engine, path, chosen, self.stop.is_set)
                        if self.stop.is_set():
                            self._video_state(v["id"], "queued")
                            continue
                        lines, suspect = _strip_repeats(lines)
                        if suspect:
                            self.log(
                                f"  {v['id']}: whisper was making things up, trimmed",
                                "warn",
                            )
                        row = write_transcript(folder, v, info, lines, meta, fmt, timestamps,
                                               o.get("ui_language", "en"))
                        with self._lock:
                            self._done += 1
                            self._finished_at.append(time.monotonic())
                            self.results[v["id"]] = row
                        self._video_state(
                            v["id"],
                            "done",
                            words=row["words"],
                            language=row["language"],
                            # the interface needs the path to actually open the
                            # file when you click on it
                            file=row["path"],
                        )
                    except Cancelled:
                        self._video_state(v["id"], "queued")
                    except Exception as e:
                        with self._lock:
                            self._errors += 1
                            self._finished_at.append(time.monotonic())
                        # translated like every other one: otherwise, depending
                        # on where it blew up, the list shows either a readable
                        # sentence or yt-dlp's raw rant
                        self._video_state(v["id"], "error",
                                          message=_explain_error(str(e))[:120])
                    finally:
                        with self._lock:
                            self._running -= 1
                        forget(path)
                        self._progress()
                finally:
                    work.task_done()

        # the transcribers start as soon as the model is ready: how many
        # depends on where it landed (two on a gpu, up to four on a cpu)
        threads = []

        def launch():
            engine_ready.wait()
            engine = box.get("engine")
            if engine is None:
                return
            for _ in range(engine.workers):
                t = threading.Thread(target=transcriber, args=(engine,), daemon=True)
                t.start()
                threads.append(t)

        launcher = threading.Thread(target=launch, daemon=True)
        launcher.start()

        videos = []
        pool = ThreadPoolExecutor(max_workers=DOWNLOADERS)
        try:
            try:
                for v in stream:
                    if self.stop.is_set():
                        break
                    with self._lock:
                        self._total += 1
                    self._video_state(v["id"], "queued", index=len(videos),
                                      title=v["title"][:110], duration=v.get("duration"),
                                      url=v["url"])
                    videos.append(v)
                    pool.submit(downloader, v)
            except TikTokError as e:
                if not videos:
                    raise
                self.log(f"the list stopped early: {e}", "warn")
            finally:
                stream.close()
                with self._lock:
                    self._listing = False
                self._progress()

            if videos and not self.stop.is_set():
                self.log(f"found {len(videos)} videos on @{handle}", "ok")
            elif not self.stop.is_set():
                raise TikTokError("the profile exists but has no visible videos")
            pool.shutdown(wait=True, cancel_futures=self.stop.is_set())
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
            # if the stop came while the downloads were being queued, the
            # model may still be loading: wait for it, then send each
            # transcriber its poison pill
            engine_ready.wait()
            launcher.join()
            left = len(threads)
            while left:
                try:
                    work.put(None, timeout=1)
                    left -= 1
                except queue.Full:
                    # A healthy worker can take much longer than one second.
                    # Wait for it; removing a queued clip here silently lost
                    # videos while the app reported a successful completed job.
                    if not self.stop.is_set() and any(t.is_alive() for t in threads):
                        continue
                    # Only cancellation or the absence of consumers permits
                    # cleanup. Never discard unfinished work as successful.
                    try:
                        spare = work.get_nowait()
                        work.task_done()
                        if spare:
                            forget(spare[1])
                            if not self.stop.is_set():
                                with self._lock:
                                    self._errors += 1
                                self._video_state(spare[0]["id"], "error",
                                                  message="The transcription worker stopped unexpectedly.")
                    except queue.Empty:
                        pass
            for t in threads:
                t.join(timeout=600)
            shutil.rmtree(tmp, ignore_errors=True)
            # 5. the two summary files, whatever happened, from everything on disk
            if self.results:
                try:
                    n = rebuild_collection(folder, handle, self.results.values(),
                                           o.get("ui_language", "en"))
                    self.log(f"wrote _ALL @{handle}.md and _index @{handle}.csv "
                             f"({n} videos in total)", "ok")
                except OSError as e:
                    self.log(f"could not write the summary files: {e}", "warn")

        self._check_stop()
        self.log(
            f"finished: {self._done} transcribed, {self._errors} failed, "
            f"{self._skipped} already done before",
            "ok" if self._done else "warn",
        )
        return folder
