#!/usr/bin/env python3
"""Render one scene through Fish Audio's timestamps endpoint (Drama 3).

    python3 scripts/fish_tts.py scenes/01-cold-open.txt outputs/01-cold-open [--language es]

The text file is sent to Drama 3 exactly as written, tags and all. If it contains
<|speaker:N|> turns, the voices come from --speakers (default: FISH_VOICE_ID for
speaker 0, FISH_CLAUDE_VOICE_ID for speaker 1).

After rendering it checks the timestamps against your text word for word and
prints any word that was skipped or added.

Writes to the output folder:
    audio.pcm    the stream exactly as Fish Audio sent it (audio.opus with --format opus)
    audio.wav    the same audio, leveled to -20 LUFS (what you upload for the avatar)
    words.json   word timestamps on the full audio timeline, in seconds
    meta.json    characters, bytes, cost, duration

Standard library only, plus ffmpeg on your PATH.
"""
import argparse
import base64
import difflib
import json
import re
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = "https://api.fish.audio/v1/tts/stream/with-timestamp"
ROOT = Path(__file__).resolve().parent.parent
PCM_RATE = 44100  # highest rate Fish Audio serves as pcm
PRICE_PER_M_BYTES = 10.00  # Drama 3 launch price; $50 after the promo


def load_env():
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def need(name):
    value = os.environ.get(name, "")
    if not value:
        sys.exit(f"{name} is empty. Fill it in .env (see .env.example).")
    return value


def spoken_words(s):
    s = re.sub(r"<\|[^|]*\|>|<[^>]*>|\[[^\]]*\]", " ", s)
    return [w for w in (re.sub(r"[^\w']", "", t.lower()) for t in s.split()) if w]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("text_file")
    p.add_argument("out_dir")
    p.add_argument("--language", default=None, help="BCP-47 tag, e.g. es or es-MX. Only affects number normalization and timestamps.")
    p.add_argument("--model", default="drama-3")
    p.add_argument("--format", default="pcm", choices=["pcm", "opus"], help="pcm = uncompressed (best quality), opus = smaller")
    p.add_argument("--volume", type=float, default=None, help="dB at the source. Negative keeps Fish Audio's output off its limiter. Defaults to FISH_VOLUME_DB in .env.")
    p.add_argument("--speakers", default="FISH_VOICE_ID,FISH_CLAUDE_VOICE_ID",
                   help="Voices for <|speaker:0|>, <|speaker:1|>, ... as .env names or voice IDs. Repeat a name to let one character borrow another's voice.")
    p.add_argument("--temperature", type=float, default=None, help="Lower sticks closer to your real voice. Defaults to FISH_TEMPERATURE in .env.")
    args = p.parse_args()

    load_env()
    if args.temperature is None and os.environ.get("FISH_TEMPERATURE"):
        args.temperature = float(os.environ["FISH_TEMPERATURE"])
    if args.volume is None and os.environ.get("FISH_VOLUME_DB"):
        args.volume = float(os.environ["FISH_VOLUME_DB"])
    key = need("FISH_API_KEY")
    text = Path(args.text_file).read_text().strip()

    if "<|speaker:" in text:
        reference_id = [need(v) if v.isupper() else v for v in args.speakers.split(",")]
    else:
        reference_id = need("FISH_VOICE_ID")

    body = {"text": text, "reference_id": reference_id, "format": args.format, "latency": "normal"}
    if args.format == "pcm":
        body["sample_rate"] = PCM_RATE
    if args.volume is not None:
        body["prosody"] = {"volume": args.volume}
    if args.language:
        body["language"] = args.language
    if args.temperature is not None:
        body["temperature"] = args.temperature

    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "model": args.model,
        },
        method="POST",
    )

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    audio = bytearray()
    alignment_by_chunk = {}

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:].strip())
                if event.get("audio_base64"):
                    audio += base64.b64decode(event["audio_base64"])
                if event.get("alignment") is not None:
                    # Each snapshot replaces the last one for its chunk_seq.
                    alignment_by_chunk[event["chunk_seq"]] = {
                        "offset": event.get("chunk_audio_offset_sec", 0.0),
                        "alignment": event["alignment"],
                    }
    except urllib.error.HTTPError as e:
        sys.exit(f"Fish Audio returned {e.code}: {e.read().decode(errors='replace')[:500]}")

    if not audio:
        sys.exit("No audio came back.")

    words = []
    for seq, item in sorted(alignment_by_chunk.items()):
        for seg in item["alignment"]["segments"]:
            words.append({
                "text": seg["text"],
                "start": round(seg["start"] + item["offset"], 3),
                "end": round(seg["end"] + item["offset"], 3),
                "chunk": seq,
            })

    # Level to -20 LUFS with a plain volume change (no compression or limiting,
    # which is what makes TTS sound crunchy), leaving headroom for the edit.
    if args.format == "pcm":
        (out / "audio.pcm").write_bytes(audio)
        src = ["-f", "s16le", "-ar", str(PCM_RATE), "-ac", "1", "-i", str(out / "audio.pcm")]
    else:
        (out / "audio.opus").write_bytes(audio)
        src = ["-i", str(out / "audio.opus")]
    stats = subprocess.run(["ffmpeg", "-hide_banner", *src, "-af", "ebur128=peak=true", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
    lufs = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", stats)[-1])
    peak = float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", stats)[-1])
    gain = min(-20.0 - lufs, -1.0 - peak)
    subprocess.run(["ffmpeg", "-y", "-v", "error", *src, "-af", f"volume={gain:.2f}dB",
                    "-ac", "1", "-c:a", "pcm_s24le", str(out / "audio.wav")], check=True)
    duration = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out / "audio.wav")],
        capture_output=True, text=True, check=True,
    ).stdout.strip())

    n_bytes = len(text.encode("utf-8"))
    meta = {
        "text_file": str(args.text_file),
        "model": args.model,
        "temperature": args.temperature,
        "language": args.language,
        "speakers": len(reference_id) if isinstance(reference_id, list) else 1,
        "characters": len(text),
        "bytes": n_bytes,
        "cost_usd": round(n_bytes * PRICE_PER_M_BYTES / 1_000_000, 4),
        "duration_sec": round(duration, 2),
        "words": len(words),
    }
    expected, got = spoken_words(text), spoken_words(" ".join(w["text"] for w in words))
    diffs = [o for o in difflib.SequenceMatcher(None, expected, got).get_opcodes() if o[0] != "equal"]
    meta["script_match"] = not diffs
    (out / "words.json").write_text(json.dumps(words, indent=1))
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta))
    for _, i1, i2, j1, j2 in diffs:
        print(f"WORD MISMATCH: script {' '.join(expected[i1:i2]) or '(nothing)'} -> audio {' '.join(got[j1:j2]) or '(nothing)'}", file=sys.stderr)
    if duration > 60:
        print(f"WARNING: {duration:.1f}s is over the 60s avatar limit. Split this scene.", file=sys.stderr)


if __name__ == "__main__":
    main()
