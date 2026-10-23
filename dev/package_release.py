"""Package the Windows app, including a hidden runtime, and verify every ZIP entry."""
import os
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def package(folder, destination):
    folder, destination = Path(folder).resolve(), Path(destination).resolve()
    binary = folder / "TikTok Transcriber.exe"
    runtime = folder / "runtime"
    if not binary.is_file() or not (runtime / "ui.html").is_file():
        raise ValueError("Expected TikTok Transcriber.exe and runtime/ui.html")
    # Only these two app artifacts: never settings, sources, backups or user files.
    files = [binary] + sorted(p for p in runtime.rglob("*") if p.is_file())
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".new")
    try:
        with ZipFile(temporary, "w", ZIP_DEFLATED, compresslevel=6) as archive:
            for path in files:
                archive.write(path, "TikTok Transcriber/" + path.relative_to(folder).as_posix())
        with ZipFile(temporary) as archive:
            names = archive.namelist()
            assert len(names) == len(files)
            assert "TikTok Transcriber/runtime/ui.html" in names
            assert "TikTok Transcriber/runtime/locales/it.json" in names
            assert archive.testzip() is None, "Corrupt ZIP entry"
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(f"OK: {len(files)} files, {destination.stat().st_size / 1048576:.1f} MB, ZIP integrity verified")


if __name__ == "__main__":
    package(*sys.argv[1:])
