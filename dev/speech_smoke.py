"""Real speech through a built app: synthesize a sentence, transcribe, check.

    python dev/speech_smoke.py <path to the built executable> <model>

The system's own voice says a known English sentence (`say` on macOS,
espeak-ng on Linux, SAPI on Windows). The built app transcribes it through
its --verify-runtime command, which downloads the model on first use, runs
the real engine and writes every export format. The check passes when the
report says so and the text contains most of the sentence's key words.

Used by the release workflow; a synthetic voice is a smoke test of the whole
pipeline, not a measure of recognition quality.
"""
import json
import os
import subprocess
import sys
import tempfile

SENTENCE = "Hello world. This is a short test of the transcriber. The weather is very nice today."
KEYWORDS = ("hello", "world", "test", "transcriber", "weather", "nice", "today")


def synthesize(folder):
    wav = os.path.join(folder, "speech.wav")
    if sys.platform == "darwin":
        aiff = os.path.join(folder, "speech.aiff")
        subprocess.run(["say", "-o", aiff, SENTENCE], check=True)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", aiff, wav], check=True)
    elif sys.platform == "win32":
        script = ("Add-Type -AssemblyName System.Speech;"
                  "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                  f"$s.SetOutputToWaveFile('{wav}'); $s.Speak('{SENTENCE}'); $s.Dispose()")
        subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)
    else:
        subprocess.run(["espeak-ng", "-s", "150", "-w", wav, SENTENCE], check=True)
    return wav


def main():
    executable, model = sys.argv[1], sys.argv[2]
    with tempfile.TemporaryDirectory(prefix="speech_smoke_") as folder:
        wav = synthesize(folder)
        report_path = os.path.join(folder, "report.json")
        result = subprocess.run([executable, "--verify-runtime", wav, report_path, model, "en"],
                                capture_output=True, text=True, timeout=1800)
        print(result.stdout[-4000:], result.stderr[-4000:], sep="\n")
        if not os.path.exists(report_path):
            raise SystemExit(f"no report (exit code {result.returncode})")
        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)
    text = report.get("text", "")
    found = [word for word in KEYWORDS if word in text.lower()]
    print(f"model {report.get('model')} on {report.get('device')} ({report.get('compute')}), "
          f"{report.get('seconds')} s, {report.get('exports')} exports")
    print(f"heard: {text!r}")
    print(f"key words: {len(found)}/{len(KEYWORDS)} {found}")
    if not report.get("passed") or report.get("exports") != 4 or len(found) < 5:
        raise SystemExit("speech smoke test failed")
    print("PASS")


if __name__ == "__main__":
    main()
