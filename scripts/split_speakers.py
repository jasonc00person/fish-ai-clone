#!/usr/bin/env python3
"""Split a multi-speaker render by speaker, using the word timestamps.

    python3 scripts/split_speakers.py scenes/03-skit.txt outputs/03-skit

Reads text + audio.wav + words.json, writes:
    turns.json     who talks when: [{speaker, start, end, text}]
    speaker0.wav   full-length track with every other speaker muted.
    speaker0-only.wav + pieces.json
                   just your turns back to back (cheaper: avatar jobs bill per
                   second). This is the audio that goes on your avatar, so your
                   face never lip-syncs someone else's lines. assemble.py
                   puts the pieces back on the full timeline afterwards.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

TURN = re.compile(r"<\|speaker:(\d+)\|>")


def clean_words(s):
    s = re.sub(r"\[[^\]]*\]", " ", s)      # [directions]
    s = re.sub(r"<[^>]*>", " ", s)          # <emphasis> and friends
    return [w for w in (re.sub(r"[^a-z0-9']", "", t.lower()) for t in s.split()) if w]


def main():
    text_file, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    text = text_file.read_text()
    words = json.loads((out_dir / "words.json").read_text())

    # Expected word sequence, each word tagged with its speaker.
    expected = []
    parts = TURN.split(text)
    for i in range(1, len(parts), 2):
        spk = int(parts[i])
        expected += [(w, spk, len(expected)) for w in clean_words(parts[i + 1])]
    if not expected:
        sys.exit("No <|speaker:N|> turns in the text.")

    # Walk the timestamps and match each one to the next expected word.
    labeled, ptr = [], 0
    for seg in words:
        toks = clean_words(TURN.sub(" ", seg["text"]))
        if not toks:
            continue
        spk = expected[min(ptr, len(expected) - 1)][1]
        for j in range(ptr, min(ptr + 6, len(expected))):
            if expected[j][0] == toks[0]:
                spk, ptr = expected[j][1], j + len(toks)
                break
        else:
            ptr += len(toks)
        labeled.append({**seg, "speaker": spk})

    turns = []
    for w in labeled:
        if turns and turns[-1]["speaker"] == w["speaker"]:
            turns[-1]["end"] = w["end"]
            turns[-1]["text"] += " " + w["text"].strip()
        else:
            turns.append({"speaker": w["speaker"], "start": w["start"], "end": w["end"], "text": w["text"].strip()})
    # Each turn owns the gap before its first word: a direction at the start of
    # a line ([laughing], [groaning], [sigh]) makes its sound there.
    duration = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out_dir / "audio.wav")],
        capture_output=True, text=True, check=True,
    ).stdout)
    for i, t in enumerate(turns):
        t["region_start"] = round(turns[i - 1]["end"] + 0.1, 3) if i > 0 else 0.0
        t["region_end"] = round(t["end"] + 0.1, 3) if i + 1 < len(turns) else round(duration, 3)
    (out_dir / "turns.json").write_text(json.dumps(turns, indent=1))

    # Full-length track with every other speaker muted.
    mutes = [(t["region_start"], t["region_end"]) for t in turns if t["speaker"] != 0]
    expr = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in mutes) or "0"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(out_dir / "audio.wav"),
         "-af", f"volume=0:enable='{expr}'", str(out_dir / "speaker0.wav")],
        check=True,
    )
    # Speaker 0's turns cut out back to back.
    pieces, at = [], 0.0
    for t in turns:
        if t["speaker"] != 0:
            continue
        a, b = t["region_start"], t["region_end"]
        pieces.append({"start": a, "end": b, "at": round(at, 3)})
        at += b - a
    (out_dir / "pieces.json").write_text(json.dumps(pieces, indent=1))
    trims = "".join(f"[0:a]atrim={p['start']}:{p['end']},asetpts=PTS-STARTPTS[p{i}];" for i, p in enumerate(pieces))
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(out_dir / "audio.wav"), "-filter_complex",
         trims + "".join(f"[p{i}]" for i in range(len(pieces))) + f"concat=n={len(pieces)}:v=0:a=1[o]",
         "-map", "[o]", str(out_dir / "speaker0-only.wav")],
        check=True,
    )

    for t in turns:
        print(f"speaker {t['speaker']}  {t['start']:6.2f} - {t['end']:6.2f}  {t['text']}")
    print(f"speaker0-only.wav: {at:.2f}s for the avatar")


if __name__ == "__main__":
    main()
