"""
offline check of the engine: no tiktok, no whisper, no window.

tiktok and the model are replaced by fakes, so everything around them gets
exercised for real: the streamed list, the download and transcription
threads, resume, stop, an engine that fails to load, the summary files, the
error messages and anonymous requests to yt-dlp.

    python dev/core_check.py
"""
import os
import shutil
import sys
import tempfile
import threading
import time

# the app lives in src/, one level up from these checks
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import tiktok_core as core  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), str(detail)))


# ------------------------------------------------------------------ links

def norm(text):
    try:
        return core.normalize_profile(text, _resolve=False)
    except core.TikTokError as e:
        return ("error", str(e))


check("a bare handle", norm("zachking")[:2] == ("https://www.tiktok.com/@zachking", "@zachking"))
check("a handle with @", norm("@zach.king")[1] == "@zach.king")
check("a profile link with a query",
      norm("https://www.tiktok.com/@zachking?lang=en")[0] == "https://www.tiktok.com/@zachking")
v = norm("https://www.tiktok.com/@zachking/video/7107337212743830830?is_from_webapp=1")
check("a video link gives the profile AND keeps the video",
      v[0] == "https://www.tiktok.com/@zachking" and v[2] and "/video/" in v[2], v)
check("tiktokuser: passes through", norm("tiktokuser:MS4wLjABAAAAabc")[0] == "tiktokuser:MS4wLjABAAAAabc")
check("nonsense is refused", norm("hello world, how are you")[0] == "error")
check("empty is refused", norm("   ")[0] == "error")

real_resolve = core._resolve_short_link
core._resolve_short_link = lambda u: "https://www.tiktok.com/@someone/video/7300000000000000001?_t=x"
s = core.normalize_profile("https://vm.tiktok.com/ZMabc123/")
core._resolve_short_link = real_resolve
check("a share link is followed to the profile",
      s[0] == "https://www.tiktok.com/@someone" and s[2], s)

# ------------------------------------------------------------------ errors

e = core._explain_error
check("login error is readable",
      "publicly available" in e("ERROR: [TikTok] 7107337212743830830: TikTok is requiring login for access"))
check("a private profile is not called a login problem",
      e("ERROR: [tiktok:user] x: This user's account is private. Log into an account that has access")
      == "private profile, nothing to be done")
check("a 404 inside a video id is not a missing profile",
      "profile" not in e("ERROR: [TikTok] 7404404404404404404: connection reset by peer"))
check("the yt-dlp prefix goes away",
      e("ERROR: [TikTok] 7107337212743830830: something odd happened") == "something odd happened",
      e("ERROR: [TikTok] 7107337212743830830: something odd happened"))
check("429 is a rate limit", "rate limiting" in e("HTTP Error 429: Too Many Requests"))

# ------------------------------------------------------------------ names

check("safe_name drops what windows forbids", core.safe_name('a<b>c:"d/e\\f|g?h*') == "abcdefgh")
check("safe_name never ends in a dot", not core.safe_name("hello" + "." * 80).endswith("."))
check("one_line flattens captions", core.one_line("first\nsecond\t third") == "first second third")

# ------------------------------------------------------------------ repeats

lines = [{"start": i, "end": i + 1, "text": "thanks for watching"} for i in range(6)]
out, suspect = core._strip_repeats(lines)
check("a looping hallucination is caught", suspect and len(out) == 1)
lines = [{"start": 0, "end": 1, "text": "hi"}, {"start": 1, "end": 2, "text": "hi"},
         {"start": 2, "end": 3, "text": "there"}, {"start": 3, "end": 4, "text": "friend"},
         {"start": 4, "end": 5, "text": "bye"}]
out, suspect = core._strip_repeats(lines)
check("consecutive duplicates collapse", not suspect and len(out) == 4)

# ------------------------------------------------------------------ files

work = tempfile.mkdtemp(prefix="core_check_")
try:
    folder = os.path.join(work, "@someone")
    os.makedirs(folder)
    speech = [{"start": 0.0, "end": 2.0, "text": "hello everybody"},
              {"start": 65.0, "end": 67.0, "text": "and goodbye"}]
    meta = {"language": "en", "confidence": 0.97}
    info = {"uploader": "someone", "duration": 70, "timestamp": 1754300000,
            "webpage_url": "https://www.tiktok.com/@someone/video/7300000000000000001"}
    video = {"id": "7300000000000000001", "title": "first\nvideo: a/b", "url": info["webpage_url"]}

    row = core.write_transcript(folder, video, info, speech, meta, "md", True)
    text = open(row["path"], encoding="utf-8").read()
    check("markdown heading stays on one line", text.splitlines()[0] == "# first video: a/b",
          text.splitlines()[0])
    check("timestamps written", "**[1:05]** and goodbye" in text)
    header, body = core._read_transcript(row["path"])
    check("reading back the text without the times", body == "hello everybody and goodbye", body)
    check("reading back the header", header.get("language") == "en"
          and header.get("duration") == "70" and header.get("url") == info["webpage_url"], header)

    # the same video again as .txt: the .md must go, not sit next to it
    row2 = core.write_transcript(folder, video, info, speech, meta, "txt", False)
    names = [f for f in os.listdir(folder) if core.TRANSCRIPT_RE.match(f)]
    check("a redo in another format replaces, it does not duplicate",
          names == [row2["file"]], names)
    header, body = core._read_transcript(row2["path"])
    check("txt read back", body == "hello everybody and goodbye"
          and header.get("date") == core._date(info["timestamp"])
          and header.get("language") == "en" and header.get("duration") == "70", (header, body))

    no_speech = core.write_transcript(
        folder, {"id": "7300000000000000002", "title": "music", "url": "u"}, {}, [], meta)
    check("no speech reads back as empty", core._read_transcript(no_speech["path"])[1] == "")

    n = core.rebuild_collection(folder, "someone", [row2, no_speech])
    everything = open(os.path.join(folder, "_ALL @someone.md"), encoding="utf-8").read()
    check("collection from disk", n == 2 and "hello everybody and goodbye" in everything, n)
    check("collection newest first",
          everything.index("## music") < everything.index("## first video"))

    # a later run that only knows about a new video must keep the old ones
    third = core.write_transcript(
        folder, {"id": "7300000000000000003", "title": "third", "url": "u3"},
        {"duration": 12}, [{"start": 0, "end": 1, "text": "three"}], meta, "md")
    n = core.rebuild_collection(folder, "@someone", [third])
    everything = open(os.path.join(folder, "_ALL @someone.md"), encoding="utf-8").read()
    index = open(os.path.join(folder, "_index @someone.csv"), encoding="utf-8-sig").read()
    check("resume keeps the earlier transcripts in the collection",
          n == 3 and "hello everybody" in everything and "three" in everything, n)
    check("the csv keeps the metadata of earlier runs",
          core._date(info["timestamp"]) in index and ";70;" in index, index)
    check("no temporary file left behind",
          not [f for f in os.listdir(folder) if f.endswith(".partial")])
    check("transcripts_on_disk ignores the summary files",
          sorted(core.transcripts_on_disk(folder)) ==
          ["7300000000000000001", "7300000000000000002", "7300000000000000003"])
finally:
    shutil.rmtree(work, ignore_errors=True)

# ------------------------------------------------------------------ anonymous requests

with core._ydl("firefox", {"cookiesfrombrowser": ("firefox",), "cookiefile": "unused"}) as y:
    check("legacy browser settings never trigger cookie reads", "cookiesfrombrowser" not in y.params)
    check("cookie files are never imported", "cookiefile" not in y.params)

# ------------------------------------------------------------------ the job


class FakeEngine:
    workers = 2
    name = "fake"

    def __init__(self, delay=0.02, language="en", confidence=0.95):
        self.delay, self.language, self.confidence = delay, language, confidence
        self.calls = []

    def transcribe(self, path, language=None):
        time.sleep(self.delay)
        self.calls.append(language)
        vid = os.path.basename(path).split(".")[0]
        return [{"start": 0, "end": 1, "text": f"spoken words of {vid}"}], {
            "language": self.language, "confidence": self.confidence}


def fake_stream(n, fail_after=None, delay=0.005):
    def stream(url, browser, limit=None, video_link=None, log=None):
        yield {"handle": "faker", "id": "MS4w"}
        for i in range(n):
            if fail_after is not None and i == fail_after:
                raise core.TikTokError("tiktok is rate limiting you")
            time.sleep(delay)
            vid = str(7400000000000000000 + i)
            yield {"id": vid, "url": f"https://www.tiktok.com/@faker/video/{vid}",
                   "title": f"video {i}", "duration": 30, "timestamp": 1754300000 - i}
            if limit and i + 1 >= limit:
                return
    return stream


def fake_download(fail_ids=(), delay=0.01):
    folders = set()
    def download(video, folder, browser, on_progress=None, cancelled=None):
        for p in (30, 60, 100):
            if cancelled and cancelled():
                raise core.Cancelled("cancelled")
            time.sleep(delay / 3)
            if on_progress:
                on_progress(p)
        if video["id"] in fail_ids:
            raise Exception("ERROR: [TikTok] 7400: HTTP Error 403: Forbidden")
        path = os.path.join(folder, video["id"] + ".mp4")
        folders.add(folder)
        with open(path, "wb") as f:
            f.write(b"x")
        return path, {"webpage_url": video["url"], "duration": 30, "uploader": "faker",
                      "timestamp": video.get("timestamp")}
    download.folders = folders
    return download




def run_job(n, engine=None, fail_ids=(), resume=True, stop_after=None, fail_after=None,
            engine_error=None, timeout=60, base=None, download_delay=0.01, limit=None):
    core.iter_profile = fake_stream(n, fail_after=fail_after)
    download = fake_download(fail_ids, delay=download_delay)
    core.download_clip = download
    events = []
    lock = threading.Lock()

    def emit(e):
        with lock:
            events.append(e)

    def provider(log):
        if engine_error:
            time.sleep(0.3)
            raise RuntimeError(engine_error)
        time.sleep(0.2)  # a model takes a moment to load
        return engine

    job = core.Transcriber({"profile": "@faker", "folder": base, "format": "md",
                            "language": "auto", "resume": resume, "limit": limit},
                           emit, engine=provider)
    t = threading.Thread(target=job.run, daemon=True)
    t0 = time.monotonic()
    t.start()
    if stop_after is not None:
        while time.monotonic() - t0 < timeout:
            with lock:
                done = sum(1 for e in events if e.get("type") == "video" and e.get("state") == "done")
            if done >= stop_after:
                job.stop.set()
                break
            time.sleep(0.01)
    t.join(timeout)
    finished = [e for e in events if e.get("type") == "finished"]
    return {"alive": t.is_alive(), "seconds": time.monotonic() - t0, "events": events,
            "finished": finished[0] if finished else None, "job": job,
            "temp_folders": set(download.folders)}


base = tempfile.mkdtemp(prefix="core_job_")
try:
    eng = FakeEngine()
    r = run_job(40, engine=eng, fail_ids={str(7400000000000000005)}, base=base)
    f = r["finished"] or {}
    folder = os.path.join(base, "@faker")
    progress = [e for e in r["events"] if e.get("type") == "progress"]
    check("a full run ends", not r["alive"] and f, f"{r['seconds']:.1f}s")
    check("39 done, 1 failed", f.get("ok") == 39 and f.get("errors") == 1, f)
    check("the failure is explained", any(
        e.get("state") == "error" and "Try again" in e.get("message", "")
        for e in r["events"] if e.get("type") == "video"))
    check("39 files on disk", len(core.transcripts_on_disk(folder)) == 39)
    check("the total grows while listing, then the listing ends",
          progress and progress[-1]["listing"] is False and progress[-1]["total"] == 40,
          progress[-1] if progress else None)
    first_dl = next(i for i, e in enumerate(r["events"])
                    if e.get("type") == "video" and e.get("state") == "downloading")
    last_queued = max(i for i, e in enumerate(r["events"])
                      if e.get("type") == "video" and e.get("state") == "queued")
    check("downloads start before the list is finished (streaming)", first_dl < last_queued,
          f"first download at event {first_dl}, last queued at {last_queued}")
    check("auto detects every clip without locking a whole profile",
          len(eng.calls) == 39 and all(c is None for c in eng.calls),
          f"{eng.calls.count(None)} clips on auto")
    # the mocked clips finish within a few milliseconds, so the estimate is
    # rightly under a second and rounds to 0 on a fast machine: what matters
    # here is that one is computed during the run (its value: "eta from the
    # real pace" below)
    check("an eta shows up", any(e.get("eta") is not None for e in progress))
    everything = os.path.join(folder, "_ALL @faker.md")
    check("the collection is written", os.path.exists(everything)
          and open(everything, encoding="utf-8").read().count("\n## ") == 39)
    check("no clip left in the temp folder",
          not [d for d in r["temp_folders"] if os.path.isdir(d) and os.listdir(d)])

    # resume: the 39 are skipped, the failed one is retried, 5 new ones come in
    r = run_job(45, engine=FakeEngine(), base=base)
    f = r["finished"] or {}
    check("resume skips what is done and retries the failed one",
          f.get("skipped") == 39 and f.get("ok") == 6, f)
    check("the collection after resume has every video",
          open(everything, encoding="utf-8").read().count("\n## ") == 45)

    # stop halfway
    shutil.rmtree(folder, ignore_errors=True)
    r = run_job(200, engine=FakeEngine(delay=0.05), base=base, stop_after=5)
    f = r["finished"] or {}
    check("stop ends the run quickly", not r["alive"] and r["seconds"] < 15,
          f"{r['seconds']:.1f}s, {f.get('ok')} done")
    check("stop is reported as such",
          any(e.get("type") == "log" and "stopped by you" in e.get("text", "") for e in r["events"]))
    check("what got done before the stop is in the collection",
          os.path.exists(everything) and f.get("ok", 0) >= 5)

    # an engine that does not load must not hang the run with the queue full
    shutil.rmtree(folder, ignore_errors=True)
    r = run_job(80, engine=None, engine_error="cuda exploded", base=base, timeout=30)
    check("an engine that fails to load ends the run, no deadlock",
          not r["alive"] and r["seconds"] < 20, f"{r['seconds']:.1f}s")
    check("and says why", any(e.get("type") == "log" and e.get("level") == "err"
                              and "cuda exploded" in e.get("text", "") for e in r["events"]))

    # tiktok stops answering halfway through the list: keep what came in
    shutil.rmtree(folder, ignore_errors=True)
    r = run_job(30, engine=FakeEngine(), base=base, fail_after=12)
    f = r["finished"] or {}
    check("a list cut halfway keeps the videos that came in",
          f.get("ok") == 12 and any("stopped early" in e.get("text", "")
                                    for e in r["events"] if e.get("type") == "log"), f)

    # low confidence detections do not decide the language
    shutil.rmtree(folder, ignore_errors=True)
    eng = FakeEngine(confidence=0.3)
    r = run_job(10, engine=eng, base=base)
    check("music-only clips get no vote on the language", all(c is None for c in eng.calls),
          eng.calls)
    # A full queue and healthy slow workers must drain completely at shutdown.
    shutil.rmtree(folder, ignore_errors=True)
    r = run_job(18, engine=FakeEngine(delay=1.5), base=base, timeout=40)
    f = r["finished"] or {}
    check("slow healthy workers never lose queued clips during shutdown",
          not r["alive"] and f.get("ok") == 18 and f.get("errors") == 0, f)
    check("every slow queued clip is exported", len(core.transcripts_on_disk(folder)) == 18)

finally:
    shutil.rmtree(base, ignore_errors=True)

# ------------------------------------------------------------------ eta

j = core.Transcriber({"profile": "x"}, lambda e: None)
now = time.monotonic()
for k in range(10):
    j._finished_at.append(now + k * 0.5)   # one every half second
check("eta from the real pace", j._eta(20) == 10, j._eta(20))

print("\n" + "=" * 70)
bad = 0
for name, ok, detail in results:
    print(f"  {'OK  ' if ok else 'FAIL'}  {name}" + (f"   [{detail[:150]}]" if detail and not ok else ""))
    bad += not ok
print("=" * 70)
print(f"  {len(results) - bad}/{len(results)} passed")
sys.exit(1 if bad else 0)
