"""Lokale Sprachnachrichten: Whisper fuer Text, eSpeak und FFmpeg fuer Audio."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from aquaticy import private_json

MAX_BYTES = 12 * 1024 * 1024
MAX_SECONDS = 90
_slot = threading.BoundedSemaphore(1)


@contextmanager
def _processing() -> Iterator[None]:
    if not _slot.acquire(timeout=2):
        raise ValueError("Die Sprachverarbeitung ist gerade beschäftigt.")
    try:
        yield
    finally:
        _slot.release()


def root() -> Path:
    from aquaticy.config import get_settings

    return get_settings().data_dir


def enabled() -> bool:
    try:
        return json.loads((root() / "voice.json").read_text(encoding="utf-8"))["enabled"] is True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def requested(text: str) -> bool:
    from aquaticy.memory_auto import own_message

    decision = False
    for clause in re.split(r"[.!?\n]+|\bsondern\b", own_message(text), flags=re.I):
        if not re.search(r"\bsprachnachricht\b", clause, re.I):
            continue
        before = re.search(
            r"\b(?:kein\w*|nicht(?!\s+nur\b)|ohne|no|not(?!\s+only\b)|don't)\b"
            r"[^.!?]{0,80}\bsprachnachricht\b", clause, re.I)
        after = re.search(r"\bsprachnachricht\b\s*(?:bitte\s+|lieber\s+|doch\s+)*"
                          r"(?:nicht|nein)\b", clause, re.I)
        if before or after:
            decision = False
        elif re.search(r"\b(?:als|schick\w*|send\w*|antworte)\b", clause, re.I):
            decision = True
    return decision


def configure(directory: Path, enable: bool) -> None:
    if enable:
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        for program in ("ffmpeg", "espeak-ng"):
            if not shutil.which(program):
                raise ValueError(f"{program} fehlt. Installiere ffmpeg und espeak-ng.")
        from faster_whisper import WhisperModel

        WhisperModel("small", device="cpu", compute_type="int8",
                     download_root=str(directory / "voice-models"))
    set_enabled(directory, enable)


def ready(directory: Path) -> bool:
    try:
        return bool(shutil.which("ffmpeg") and shutil.which("espeak-ng")
                    and importlib.util.find_spec("faster_whisper")
                    and next((p for p in (directory / "voice-models").rglob("model.bin")
                              if p.is_file() and p.stat().st_size > 0), None))
    except (OSError, ImportError, ValueError):
        return False


def set_enabled(directory: Path, enable: bool) -> None:
    if enable and not ready(directory):
        raise ValueError("Sprachnachrichten zuerst im Terminal mit aquaticy voice einrichten.")
    private_json.write(directory / "voice.json", {"enabled": enable})


def transcribe(data: bytes) -> str:
    if not enabled() or not 0 < len(data) <= MAX_BYTES:
        raise ValueError("Sprachnachricht deaktiviert oder zu groß.")
    with _processing(), tempfile.TemporaryDirectory(prefix="aquaticy-voice-") as temp:
        source = Path(temp) / "input"
        source.write_bytes(data)
        result = subprocess.run(
            [sys.executable, "-m", "aquaticy.voice", str(source), str(root() / "voice-models")],
            capture_output=True, text=True, timeout=180, check=True,
            env=dict(os.environ, HF_HUB_DISABLE_TELEMETRY="1", HF_HUB_OFFLINE="1"))
        text = result.stdout.strip()[:4000]
        if not text:
            raise ValueError("Keine Sprache erkannt.")
        return text


def synthesize(text: str) -> bytes:
    if not enabled():
        raise ValueError("Sprachnachrichten sind aus.")
    with _processing(), tempfile.TemporaryDirectory(prefix="aquaticy-voice-") as temp:
        wav, opus = Path(temp) / "speech.wav", Path(temp) / "speech.ogg"
        spoken = subprocess.run(["espeak-ng", "-v", "de", "--stdin", "--stdout"],
                                input=text[:1800].encode(), capture_output=True,
                                timeout=30, check=True)
        wav.write_bytes(spoken.stdout)
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(wav), "-t", "90",
                        "-c:a", "libopus", "-b:a", "32k", str(opus)],
                       capture_output=True, timeout=30, check=True)
        if opus.stat().st_size > MAX_BYTES:
            raise ValueError("Audio zu groß.")
        return opus.read_bytes()


def _recognize(source: Path, models: Path) -> None:
    from faster_whisper import WhisperModel

    with tempfile.TemporaryDirectory(prefix="aquaticy-decode-") as temp:
        wav = Path(temp) / "input.wav"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error",
                        "-protocol_whitelist", "file,pipe",
                        "-format_whitelist", "ogg,wav,mp3,mov,aac", "-i", str(source),
                        "-t", str(MAX_SECONDS + 1), "-ar", "16000", "-ac", "1", str(wav)],
                       capture_output=True, timeout=30, check=True)
        import wave

        with wave.open(str(wav)) as audio:
            if audio.getnframes() / audio.getframerate() > MAX_SECONDS:
                raise ValueError("Sprachnachricht länger als 90 Sekunden.")
        model = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=2,
                             download_root=str(models), local_files_only=True)
        segments, _ = model.transcribe(str(wav), beam_size=1)
        print(" ".join(segment.text for segment in segments)[:4000])


if __name__ == "__main__":
    _recognize(Path(sys.argv[1]), Path(sys.argv[2]))
