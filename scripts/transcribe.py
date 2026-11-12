#!/usr/bin/env python3
"""Transcribe a video or audio file with Fish Audio, with a time for every word.

    python3 scripts/transcribe.py take.mp4
    python3 scripts/transcribe.py take.mp4 --find "it took me twenty minutes"
    python3 scripts/transcribe.py take.mp4 --start 60 --end 120 --out outputs/take-words.json

Use it to find a flubbed line in a take (--find prints where those words are),
to write the transcripts for voice clips, or to check that a generated clip says
what the script says. Costs about $0.36 per hour of audio from your API credit.
"""
import argparse
import difflib
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from align import norm  # noqa: E402
from common import ffmpeg, fish_request, load_env, multipart, need, require_ffmpeg  # noqa: E402


def transcribe(path, start=None, end=None, language=None, key=None):
    """{'text', 'events', 'duration', 'segments': [{text, start, end}], 'speakers': n}.

    Times are on the source file's clock. `events` lists the sounds the model heard
    besides words, such as music or laughter; `text` has them removed.
    """
    key = key or need("FISH_API_KEY")
    with tempfile.TemporaryDirectory() as tmp:
        audio = Path(tmp) / "audio.m4a"
        trim = (["-ss", str(start)] if start else []) + (["-to", str(end)] if end else [])
        ffmpeg(*trim, "-i", path, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "aac", "-b:a", "48k", audio)
        fields = [("ignore_timestamps", "false")] + ([("language", language)] if language else [])
        body, content_type = multipart(fields, [("audio", "audio.m4a", audio.read_bytes())])
    with fish_request("/v1/asr", key, data=body, headers={"Content-Type": content_type, "model": "transcribe-1-pro"},
                      timeout=600) as resp:
        data = json.loads(resp.read())
    shift = start or 0.0
    segments = [{"text": s["text"], "start": round(s["start"] + shift, 3), "end": round(s["end"] + shift, 3)}
                for s in data.get("segments", [])]
    speakers = {t.get("speaker") for t in data.get("speaker_turns", [])}
    raw = re.sub(r"<\|[^|]*\|>", " ", data.get("text", ""))
    events = sorted({e.lower() for e in re.findall(r"\[([^\]]*)\]", raw)})
    text = " ".join(re.sub(r"\[[^\]]*\]", " ", raw).split())
    segments = [s for s in segments if not re.fullmatch(r"\s*\[[^\]]*\]\s*", s["text"])]
    return {"text": text, "events": events, "duration": data.get("duration"), "segments": segments,
            "speakers": max(len(speakers), 1)}


def find(segments, phrase):
    """(start, end, matched text) of the stretch that best matches the phrase, or None."""
    want = [norm(w) for w in phrase.split() if norm(w)]
    words = [(norm(s["text"]), s) for s in segments if norm(s["text"])]
    if not want or not words:
        return None
    best, span = 0.0, None
    for i in range(len(words)):
        for n in (len(want), len(want) - 1, len(want) + 1, len(want) + 2):
            window = words[i:i + n]
            if n < 1 or len(window) < n:
                continue
            ratio = difflib.SequenceMatcher(None, want, [w for w, _ in window], autojunk=False).ratio()
            if ratio > best:
                best, span = ratio, window
    if best < 0.6:
        return None
    return span[0][1]["start"], span[-1][1]["end"], " ".join(s["text"].strip() for _, s in span)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file")
    p.add_argument("--start", type=float, default=None)
    p.add_argument("--end", type=float, default=None)
    p.add_argument("--language", default=None, help="ISO 639-1 hint such as en or es (it detects the language anyway)")
    p.add_argument("--find", default=None, help="words to locate; prints their start and end time")
    p.add_argument("--out", default=None, help="write the full result (text + word times) to this JSON file")
    a = p.parse_args()
    require_ffmpeg()
    load_env()
    if not Path(a.file).is_file():
        sys.exit(f"No such file: {a.file}")

    result = transcribe(a.file, a.start, a.end, a.language)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(result, indent=1))
    if a.find:
        hit = find(result["segments"], a.find)
        if not hit:
            sys.exit(f"Could not find \"{a.find}\" in the audio. Transcript:\n{result['text']}")
        print(f"{hit[0]:.2f} - {hit[1]:.2f}  {hit[2]}")
    else:
        print(result["text"])
        if result["speakers"] > 1:
            print(f"({result['speakers']} speakers heard)", file=sys.stderr)
        if result["events"]:
            print(f"(also heard: {', '.join(result['events'])})", file=sys.stderr)


if __name__ == "__main__":
    main()
