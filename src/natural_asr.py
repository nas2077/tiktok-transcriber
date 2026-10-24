"""Local Qwen ASR, Silero voice detection and SpeechBrain language changes.

The distributed runtime is transcribe.cpp (CPU/Vulkan). Times identify actual
audio block starts; they are not model-aligned word timestamps. No text editor
or second language model rewrites the recognized words.
"""
import logging
import os
import threading
from functools import lru_cache

import numpy as np

SAMPLE_RATE = 16000
MAX_BLOCK_SECONDS = 90


class TranscriptionCancelled(Exception):
    pass


@lru_cache(maxsize=1)
def native_runtime():
    import transcribe_cpp as native
    native.set_log_callback(lambda level, message: logging.getLogger("natural_asr.native").debug(message.rstrip()))
    return native


def _quiet_boundary(audio, lower, upper, preferred):
    """Choose a low-energy cut near a proposed boundary, in original samples."""
    lower, upper = max(0, int(lower)), min(len(audio), int(upper))
    width = 1600  # 100 ms: favor a real short pause, not one zero crossing.
    if upper - lower < width * 2:
        return int(np.clip(preferred, lower, upper))
    starts = np.arange(lower, upper - width + 1, 320)
    powers = np.array([np.mean(np.square(audio[a:a + width], dtype=np.float64)) for a in starts])
    # Keep the cut near its target when multiple intervals have similar energy.
    floor = powers.min()
    candidates = starts[powers <= max(floor * 2, 1e-7)] + width // 2
    return int(min(candidates, key=lambda a: abs(a - preferred)))


def audio_blocks(audio, speech, changes=()):
    """Retain context around detected speech and all audio across internal cuts.

    Silero can miss an unvoiced opening syllable. Cropping every VAD island
    independently discarded words in the prototype. Instead, use VAD to gate
    silence and delimit long gaps, keeping a full second of extra edge context.
    """
    if not speech:
        return []
    # A substantial silence is a safe cut even if language identification is
    # uncertain. With Silero's padding already included, this is a real gap.
    changes = list(changes) + [(a["end"] + b["start"]) // 2 for a, b in zip(speech, speech[1:])
                               if b["start"] - a["end"] >= int(.35 * SAMPLE_RATE)]
    context = SAMPLE_RATE
    spans = []
    for part in speech:
        a = max(0, part["start"] - context)
        b = min(len(audio), part["end"] + context)
        if spans and a <= spans[-1][1]:
            spans[-1][1] = b
        else:
            spans.append([a, b])
    blocks = []
    for start, end in spans:
        # Language boundaries take priority over length cuts.
        boundaries = [start] + sorted(set(int(c) for c in changes if start + SAMPLE_RATE < c < end - SAMPLE_RATE)) + [end]
        for a, b in zip(boundaries, boundaries[1:]):
            while b - a > MAX_BLOCK_SECONDS * SAMPLE_RATE:
                preferred = a + (MAX_BLOCK_SECONDS - 2) * SAMPLE_RATE
                cut = _quiet_boundary(audio, preferred - 3 * SAMPLE_RATE,
                                      min(b - SAMPLE_RATE, a + MAX_BLOCK_SECONDS * SAMPLE_RATE), preferred)
                blocks.append((a, cut))
                a = cut
            if b > a:
                blocks.append((a, b))
    return blocks


class NaturalEngine:
    """One serialized native model/session, shared by profile and gallery jobs."""
    workers = 1  # Native sessions share a model-wide compute lock and GPU memory.

    def __init__(self, model_path, language_path, log, backend="auto"):
        native = native_runtime()
        self._native, self._log = native, log
        self._path = model_path
        self._lock = threading.Lock()
        self._model = self._session = self._lid_model = self._lid = None
        self.compute = "Q8_0"
        try:
            try:
                self._load(backend)
            except (native.BackendError, native.OutOfMemory):
                if backend == "cpu":
                    raise
                self._release_asr()
                log("The graphics card could not run Natural. Retrying on the processor.", "warn")
                self._load("cpu")
            # Language ID is small and stays on CPU; no GPU contention with ASR.
            self._lid_model = native.Model(language_path, backend="cpu")
            self._lid = self._lid_model.langid_session(n_threads=2)
        except Exception:
            self.close()
            raise

    def _load(self, backend):
        self._model = self._native.Model(self._path, backend=backend)
        self.device = self._model.device.kind
        self._session = self._model.session(n_threads=6)
        self._session.run(np.zeros(SAMPLE_RATE, dtype=np.float32))

    def _release_asr(self):
        for attribute in ("_session", "_model"):
            item = getattr(self, attribute, None)
            if item is not None:
                item.close()
                setattr(self, attribute, None)

    def close(self):
        self._release_asr()
        for attribute in ("_lid", "_lid_model"):
            item = getattr(self, attribute, None)
            if item is not None:
                item.close()
                setattr(self, attribute, None)

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _language_changes(self, audio, speech, check=lambda: None):
        if len(audio) < SAMPLE_RATE * 7:
            return []
        supported = set(self._model.capabilities.languages)
        probes = []
        # Score overlapping 4-second windows only where actual voice is present.
        for a in range(max(0, speech[0]["start"] - SAMPLE_RATE), speech[-1]["end"], SAMPLE_RATE * 2):
            check()
            b = min(len(audio), a + 4 * SAMPLE_RATE)
            if b - a < SAMPLE_RATE:
                continue
            voiced = sum(max(0, min(b, s["end"]) - max(a, s["start"])) for s in speech)
            if voiced < SAMPLE_RATE:
                continue
            prediction = self._lid.run(np.ascontiguousarray(audio[a:b]))
            if not prediction.candidates:
                continue
            best = prediction.candidates[0]
            code = {"tl": "fil", "iw": "he", "jw": "jv"}.get(best.code, best.code)
            if code in supported and best.p >= .8:
                probes.append((a + (b - a) // 2, code))
        # Require two consecutive confident probes before accepting a new
        # language, so one English product name cannot split an Italian video.
        stable = []
        for i in range(1, len(probes)):
            if probes[i][1] == probes[i - 1][1] and probes[i][0] - probes[i - 1][0] <= 5 * SAMPLE_RATE:
                if not stable or probes[i][1] != stable[-1][1]:
                    stable.append((probes[i - 1][0], probes[i][1]))
        changes = []
        for (_, old), (center, new) in zip(stable, stable[1:]):
            if old == new:
                continue
            previous = max((t for t, code in probes if t < center and code == old), default=center - 2 * SAMPLE_RATE)
            midpoint = (previous + center) // 2
            # A non-voice gap gives a better boundary than energy alone.
            gaps = [(x["end"] + y["start"]) // 2 for x, y in zip(speech, speech[1:])
                    if x["end"] <= y["start"] and previous - SAMPLE_RATE <= (x["end"] + y["start"]) // 2 <= center + SAMPLE_RATE]
            cut = min(gaps, key=lambda g: abs(g - midpoint)) if gaps else _quiet_boundary(
                audio, midpoint - SAMPLE_RATE, midpoint + SAMPLE_RATE, midpoint)
            changes.append(cut)
        return changes

    def transcribe(self, path, language=None, cancelled=None):
        from faster_whisper.audio import decode_audio
        from faster_whisper.vad import VadOptions, get_speech_timestamps
        audio = (decode_audio(path, sampling_rate=SAMPLE_RATE) if isinstance(path, (str, bytes, os.PathLike)) or hasattr(path, "read")
                 else np.asarray(path, dtype=np.float32))
        audio = np.ascontiguousarray(audio, dtype=np.float32)
        forced = None if language in (None, "auto") else language
        def check():
            if cancelled and cancelled():
                raise TranscriptionCancelled()

        check()
        while not self._lock.acquire(timeout=.1):
            check()
        try:
            check()
            if self._session is None:
                # an earlier fallback to the processor failed halfway: load
                # again instead of failing every video after it
                self._load("cpu")
            supported = set(self._model.capabilities.languages)
            if forced and supported and forced not in supported:
                forced = None   # a language Qwen does not know: let it detect
            speech = get_speech_timestamps(audio, VadOptions(min_speech_duration_ms=100, min_silence_duration_ms=700))
            if not speech:
                return [], {"language": "", "confidence": 0}
            changes = [] if forced else self._language_changes(audio, speech, check)
            blocks = audio_blocks(audio, speech, changes)
            finished = threading.Event()

            def watch_cancel():
                while not finished.wait(.05):
                    if cancelled and cancelled():
                        session = self._session
                        if session is not None:
                            session.cancel()
                            return

            watcher = threading.Thread(target=watch_cancel, daemon=True) if cancelled else None
            if watcher:
                watcher.start()
            try:
                try:
                    lines = self._decode(audio, blocks, forced, check)
                except (self._native.BackendError, self._native.OutOfMemory):
                    check()
                    if self.device == "cpu":
                        raise
                    # Discard the partial attempt and redo the same blocks once.
                    # No mixed-backend duplicate text can escape this method.
                    self._release_asr()
                    self._log("The graphics card could not run Natural. Retrying on the processor.", "warn")
                    self._load("cpu")
                    lines = self._decode(audio, blocks, forced, check)
                except self._native.Aborted:
                    check()
                    raise
                check()
            finally:
                finished.set()
                if watcher:
                    watcher.join()
            languages = list(dict.fromkeys(row["language"] for row in lines if row["language"]))
            return lines, {"language": "+".join(languages), "confidence": None if lines else 0}
        finally:
            self._lock.release()

    def _decode(self, audio, blocks, language, check=lambda: None):
        lines = []
        for a, b in blocks:
            check()
            try:
                result = self._session.run(np.ascontiguousarray(audio[a:b]), language=language)
            except self._native.Aborted:
                check()
                raise
            text = " ".join(result.text.split())
            if text:
                lines.append({"start": a / SAMPLE_RATE, "end": b / SAMPLE_RATE, "text": text,
                              "language": language or result.language or ""})
        return lines
