"""Explicit release verification command; never runs on ordinary app startup."""
import faulthandler
import hashlib
import json
import os
import sys
import tempfile
import time

import tiktok_core as core


def run(audio, report_path, model=core.DEFAULT_MODEL, language="auto"):
    # a verification that hangs says where, instead of waiting forever
    faulthandler.dump_traceback_later(900, exit=True)
    begin = time.perf_counter()
    engine = core.Engine(model, log=lambda text, *a: print(text, file=sys.stderr, flush=True))
    lines, meta = engine.transcribe(audio, language)
    report = {"passed": False, "model": engine.name, "device": engine.device,
              "compute": engine.compute, "lines": lines, "meta": meta,
              "text": " ".join(r["text"] for r in lines), "exports": 0}
    with open(audio, "rb") as stream:
        report["audio_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    with tempfile.TemporaryDirectory(prefix="tiktok_runtime_check_") as folder:
        video = {"id": "7690000000000000000", "title": "Runtime verification", "url": ""}
        for fmt in ("md", "txt"):
            for timestamps in (False, True):
                row = core.write_transcript(folder, video, {}, lines, meta, fmt, timestamps, "it")
                header, body = core._read_transcript(row["path"])
                assert " ".join(body.split()) == report["text"]
                assert header["language"] == meta["language"]
                core.rebuild_collection(folder, "runtime", ui_language="it")
                assert os.path.isfile(os.path.join(folder, "_ALL @runtime.md"))
                report["exports"] += 1
    report["seconds"] = round(time.perf_counter() - begin, 4)
    report["passed"] = True
    core._atomic_write(report_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
