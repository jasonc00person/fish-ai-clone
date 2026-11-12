#!/usr/bin/env python3
"""Split a multi-speaker render by speaker, using the word timestamps.

    python3 scripts/split_speakers.py outputs/my-video/03-skit

Reads the scene folder's scene.txt + audio.wav + words.json (from fish_tts.py), writes:
    turns.json     who talks when: [{speaker, start, end, text, region_start, region_end}]
    speaker0.wav   full-length track with every other speaker muted.
    speaker0-only.wav + pieces.json
                   just your turns back to back (cheaper: avatar jobs bill per
                   second). This is the audio that goes on your avatar, so your
                   face never lip-syncs someone else's lines. assemble.py
                   puts the pieces back on the full timeline afterwards.

The old form still works: split_speakers.py <text file> <scene folder>.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from align import align, turns as group_turns  # noqa: E402
from common import duration, ffmpeg, require_ffmpeg  # noqa: E402


def main():
    if len(sys.argv) not in (2, 3) or sys.argv[1] in ("-h", "--help"):
        sys.exit(__doc__)
    require_ffmpeg()
    out_dir = Path(sys.argv[-1])
    text_file = Path(sys.argv[1]) if len(sys.argv) == 3 else out_dir / "scene.txt"
    if not text_file.is_file():
        sys.exit(f"No script text at {text_file}. Pass it first: split_speakers.py <text file> <scene folder>")
    text = text_file.read_text()
    if "<|speaker:" not in text:
        sys.exit("No <|speaker:N|> turns in the text.")
    words = json.loads((out_dir / "words.json").read_text())

    turns = group_turns(align(text, words))
    # Each turn owns the gap before its first word: a direction at the start of
    # a line ([laughing], [groaning], [sigh]) makes its sound there.
    total = duration(out_dir / "audio.wav")
    # The boundary sits just after the previous line, but never inside the next one's first word.
    bounds = [0.0] + [round(min(a["end"] + 0.1, (a["end"] + b["start"]) / 2), 3) for a, b in zip(turns, turns[1:])]
    bounds.append(round(total, 3))
    for i, t in enumerate(turns):
        t["region_start"], t["region_end"] = bounds[i], bounds[i + 1]
    (out_dir / "turns.json").write_text(json.dumps(turns, indent=1))

    # Full-length track with every other speaker muted.
    mutes = [(t["region_start"], t["region_end"]) for t in turns if t["speaker"] != 0]
    expr = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in mutes) or "0"
    ffmpeg("-i", out_dir / "audio.wav", "-af", f"volume=0:enable='{expr}'", out_dir / "speaker0.wav")

    # Speaker 0's turns cut out back to back.
    pieces, at = [], 0.0
    for t in turns:
        if t["speaker"] != 0:
            continue
        a, b = t["region_start"], t["region_end"]
        pieces.append({"start": a, "end": b, "at": round(at, 3)})
        at += b - a
    if not pieces:
        sys.exit("Speaker 0 never talks in this scene, so there is nothing to put on your face.")
    (out_dir / "pieces.json").write_text(json.dumps(pieces, indent=1))
    trims = "".join(f"[0:a]atrim={p['start']}:{p['end']},asetpts=PTS-STARTPTS[p{i}];" for i, p in enumerate(pieces))
    ffmpeg("-i", out_dir / "audio.wav", "-filter_complex",
           trims + "".join(f"[p{i}]" for i in range(len(pieces))) + f"concat=n={len(pieces)}:v=0:a=1[o]",
           "-map", "[o]", out_dir / "speaker0-only.wav")

    for t in turns:
        print(f"speaker {t['speaker']}  {t['start']:6.2f} - {t['end']:6.2f}  {t['text']}")
    print(f"speaker0-only.wav: {at:.2f}s for the avatar")


if __name__ == "__main__":
    main()
