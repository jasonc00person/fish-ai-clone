#!/usr/bin/env python3
"""Render one scene through Fish Audio's timestamps endpoint (Drama 3).

    python3 scripts/fish_tts.py scenes/my-video/01-hook.txt outputs/my-video/01-hook
    python3 scripts/fish_tts.py scenes/my-video/01-hook.txt outputs/my-video/01-hook --takes 3
    python3 scripts/fish_tts.py scenes/my-video/01-hook.txt outputs/my-video/01-hook --pick 2

The text file is sent to Drama 3 exactly as written, tags and all. If it contains
<|speaker:N|> turns, the voices come from --speakers (default: FISH_VOICE_ID for
speaker 0, FISH_CLAUDE_VOICE_ID for speaker 1).

After rendering it checks the timestamps against your text word for word and
prints any word that was skipped or added.

--takes N renders the scene N times (one after another, so nothing gets rate
limited), measures each take (pitch per speaker, how far any whisper drops) and
puts the best one in the output folder. Takes differ a lot even at a low
temperature, and each one costs a fraction of a cent, so this is the cheap way
to get the read you wanted. All takes stay in <out>/takes/; --pick N swaps a
different one in without rendering again.

Writes to the output folder:
    audio.pcm    the stream exactly as Fish Audio sent it (audio.opus with --format opus)
    audio.wav    the same audio, leveled to -20 LUFS (what you upload for the avatar)
    words.json   word timestamps on the full audio timeline, in seconds
    meta.json    characters, bytes, cost, duration
    scene.txt    the text that was sent

Standard library only, plus ffmpeg on your PATH.
"""
import argparse
import base64
import datetime
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from align import mismatches  # noqa: E402
from common import (API, ROOT, duration, explain_http_error, ffmpeg, level_gain, load_env, need,  # noqa: E402,F401
                    require_ffmpeg)

ENDPOINT = API + "/v1/tts/stream/with-timestamp"
PCM_RATE = 44100  # highest rate Fish Audio serves as pcm (48000 returns a 400)
TARGET_LUFS = -20.0
FILES = ("audio.pcm", "audio.opus", "audio.wav", "words.json", "meta.json", "scene.txt")


def price_per_million_bytes(model):
    """USD per million UTF-8 bytes. Drama 3 is $50; the launch price of $10 runs through November 30, 2026.

    Only used for the cost shown, never for billing. Set FISH_PRICE_PER_MILLION in .env if the price changes.
    """
    if os.environ.get("FISH_PRICE_PER_MILLION"):
        try:
            return float(os.environ["FISH_PRICE_PER_MILLION"])
        except ValueError:
            pass
    if model == "drama-3":
        return 10.0 if datetime.date.today() < datetime.date(2026, 12, 1) else 50.0
    return 0.0 if model.endswith("-free") else None


def stream(body, key, model, attempts=3):
    """POST the request and return (audio bytes, {chunk_seq: {offset, alignment}})."""
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json", "model": model})
    for attempt in range(1, attempts + 1):
        audio, alignment = bytearray(), {}
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
                        alignment[event["chunk_seq"]] = {"offset": event.get("chunk_audio_offset_sec", 0.0),
                                                         "alignment": event["alignment"]}
            if audio:
                return bytes(audio), alignment
            problem = "No audio came back."
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504):
                sys.exit(explain_http_error(e))
            problem = f"Fish Audio returned {e.code}."
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            problem = f"Connection problem ({getattr(e, 'reason', e)})."
        if attempt < attempts:
            print(f"{problem} Trying again in {5 * attempt}s.", file=sys.stderr)
            time.sleep(5 * attempt)
    sys.exit(f"{problem} Gave up after {attempts} tries. Nothing was saved for this take.")


def render(text, body, key, args, out):
    """One render into the folder `out`. Returns its meta dict."""
    out.mkdir(parents=True, exist_ok=True)
    audio, alignment = stream(body, key, args.model)

    words = []
    for seq, item in sorted(alignment.items()):
        for seg in item["alignment"]["segments"]:
            words.append({"text": seg["text"], "start": round(seg["start"] + item["offset"], 3),
                          "end": round(seg["end"] + item["offset"], 3), "chunk": seq})

    # Level to -20 LUFS with a plain volume change (no compression or limiting,
    # which is what makes TTS sound crunchy), leaving headroom for the edit.
    if args.format == "pcm":
        (out / "audio.pcm").write_bytes(audio)
        src = ["-f", "s16le", "-ar", str(PCM_RATE), "-ac", "1", "-i", str(out / "audio.pcm")]
    else:
        (out / "audio.opus").write_bytes(audio)
        src = ["-i", str(out / "audio.opus")]
    gain = level_gain(src, TARGET_LUFS)
    ffmpeg(*src, "-af", f"volume={gain:.2f}dB", "-ac", "1", "-c:a", "pcm_s24le", out / "audio.wav")
    seconds = duration(out / "audio.wav")

    n_bytes = len(text.encode("utf-8"))
    price = price_per_million_bytes(args.model)
    diffs = mismatches(text, words)
    meta = {
        "text_file": str(args.text_file),
        "model": args.model,
        "temperature": body.get("temperature"),
        "language": body.get("language"),
        "speakers": len(body["reference_id"]) if isinstance(body["reference_id"], list) else 1,
        "characters": len(text),
        "bytes": n_bytes,
        "cost_usd": None if price is None else round(n_bytes * price / 1_000_000, 4),
        "duration_sec": round(seconds, 2),
        "words": len(words),
        "script_match": not diffs,
        "mismatches": [f"script '{a or '(nothing)'}' -> audio '{b or '(nothing)'}'" for a, b in diffs],
    }
    (out / "words.json").write_text(json.dumps(words, indent=1))
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    (out / "scene.txt").write_text(text + "\n")
    return meta


def measure(take_dir, text, speakers):
    """Pitch and whisper numbers for one take, or None if measuring fails."""
    try:
        from voice_check import check, expected_pitch
        return check(take_dir, text=text, expect=expected_pitch(speakers))
    except Exception as e:  # measuring is a bonus; never lose a paid render over it
        print(f"(could not measure {take_dir}: {e})", file=sys.stderr)
        return None


def score(meta, report):
    """Lower is better: words wrong, then anything flagged, then pitch drift, then a weak whisper."""
    if report is None:  # a take nobody could check never beats one that was checked
        return (not meta["script_match"], float("inf"), float("inf"), 0.0)
    drift = max([abs(t.get("off_pct", 0)) for t in report["turns"]] or [0])
    whisper = min([w["drop_db"] for w in report["whispers"]] or [0.0])
    return (not meta["script_match"], len(report["flags"]), drift, -whisper)


def put_in_place(take_dir, out):
    for name in FILES:
        if (out / name).exists():
            (out / name).unlink()
        if (take_dir / name).exists():
            shutil.copy2(take_dir / name, out / name)
    (out / "picked.txt").write_text(f"take {take_dir.name}\n")


def report_scene(meta):
    print(json.dumps({k: v for k, v in meta.items() if k != "mismatches"}))
    for line in meta["mismatches"]:
        print(f"WORD MISMATCH: {line}", file=sys.stderr)
    if meta["duration_sec"] > 59:
        print(f"NOTE: {meta['duration_sec']:.1f}s is longer than one avatar job takes (about 59s). "
              f"Split it at sentence breaks: python3 scripts/chunk_scene.py <this folder>", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("text_file")
    p.add_argument("out_dir")
    p.add_argument("--takes", type=int, default=1, help="render this many takes and keep the best (3 is plenty; 6 for a two-voice scene)")
    p.add_argument("--pick", type=int, default=None, help="put an already rendered take in place instead of rendering")
    p.add_argument("--language", default=None, help="BCP-47 tag, e.g. es or es-MX. Only affects number normalization and timestamps.")
    p.add_argument("--model", default="drama-3", help="drama-3 (default). s2.1-pro-free is free, for testing the setup without API credit.")
    p.add_argument("--format", default="pcm", choices=["pcm", "opus"], help="pcm = uncompressed (best quality), opus = smaller")
    p.add_argument("--volume", type=float, default=None, help="dB at the source. Negative keeps Fish Audio's output off its limiter. Defaults to FISH_VOLUME_DB in .env.")
    p.add_argument("--speakers", default="FISH_VOICE_ID,FISH_CLAUDE_VOICE_ID",
                   help="Voices for <|speaker:0|>, <|speaker:1|>, ... as .env names or voice IDs. Repeat a name to let one character borrow another's voice.")
    p.add_argument("--temperature", type=float, default=None, help="Lower sticks closer to your real voice. Defaults to FISH_TEMPERATURE in .env. Use 0.15 for two-voice scenes.")
    args = p.parse_args()

    require_ffmpeg()
    load_env()
    out = Path(args.out_dir)
    speakers = args.speakers.split(",")

    if args.pick is not None:
        take_dir = out / "takes" / str(args.pick)
        if not (take_dir / "audio.wav").exists():
            sys.exit(f"No take {args.pick} in {out / 'takes'}.")
        put_in_place(take_dir, out)
        print(f"Take {args.pick} is now the scene's audio.")
        report_scene(json.loads((out / "meta.json").read_text()))
        return

    if args.temperature is None and os.environ.get("FISH_TEMPERATURE"):
        args.temperature = float(os.environ["FISH_TEMPERATURE"])
    if args.volume is None and os.environ.get("FISH_VOLUME_DB"):
        args.volume = float(os.environ["FISH_VOLUME_DB"])
    key = need("FISH_API_KEY")
    if not Path(args.text_file).is_file():
        sys.exit(f"No such file: {args.text_file}")
    text = Path(args.text_file).read_text().strip()
    if not text:
        sys.exit(f"{args.text_file} is empty.")

    if "<|speaker:" in text:
        import re
        highest = max(int(n) for n in re.findall(r"<\|speaker:(\d+)\|>", text))
        if highest >= len(speakers):
            sys.exit(f"The text uses <|speaker:{highest}|> but --speakers lists only {len(speakers)} voices.")
        reference_id = [need(v) if v.isupper() else v for v in speakers]
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

    if args.takes <= 1:
        report_scene(render(text, body, key, args, out))
        return

    results = []
    existing = [int(d.name) for d in (out / "takes").iterdir() if d.name.isdigit()] if (out / "takes").is_dir() else []
    first = max(existing, default=0) + 1
    for n in range(first, first + args.takes):
        take_dir = out / "takes" / str(n)
        meta = render(text, body, key, args, take_dir)
        report = measure(take_dir, text, speakers)
        results.append((n, meta, report))
        pitch = ", ".join(f"spk{s} {hz:.0f} Hz" for s, hz in sorted((report or {}).get("pitch_by_speaker", {}).items()))
        whisper = ", ".join(f"whisper -{w['drop_db']} dB" for w in (report or {}).get("whispers", []))
        flags = "; ".join((report or {}).get("flags", []))
        print(f"take {n}: {meta['duration_sec']:.1f}s  words {'ok' if meta['script_match'] else 'MISMATCH'}"
              f"{'  ' + pitch if pitch else ''}{'  ' + whisper if whisper else ''}{'  CHECK: ' + flags if flags else ''}")

    best = min(results, key=lambda r: score(r[1], r[2]))
    put_in_place(out / "takes" / str(best[0]), out)
    total = sum(m["cost_usd"] or 0 for _, m, _ in results)
    print(f"Picked take {best[0]} by the numbers ({len(results)} takes, ${total:.4f}). "
          f"Listen before you trust it; swap with --pick N.")
    report_scene(best[1])


if __name__ == "__main__":
    main()
