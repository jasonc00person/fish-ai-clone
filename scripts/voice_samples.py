#!/usr/bin/env python3
"""Pull clean voice clips out of footage you already have, ready to clone.

    python3 scripts/voice_samples.py ~/Videos/episode-12.mp4 ~/Videos/episode-13.mp4
    python3 scripts/voice_samples.py me/source.wav --clips 4

Give it one or more videos or recordings of you talking. It finds stretches of
steady speech (15 to 30 seconds, starting and ending on a pause), cuts the best
ones into me/voice/clip-1.wav, clip-2.wav, ... and writes each clip's transcript
next to it (clip-1.txt), which is what makes the clone pronounce things your way.
Clips where a second person talks, or where music or other sounds were heard,
are skipped.

It favors the start of each file: the first lines of a video are usually you at
the energy you want the clone to have. Aim for 1 to 2 minutes total across 3 to
5 clips, from more than one recording if you can.

Before cloning, read the .txt files and fix any names the transcription
misheard (brand names especially). Then:

    python3 scripts/clone_voice.py "My AI Voice" me/voice/*.wav

Transcription costs about a cent per run from your API credit. --no-transcribe
skips it (then write the .txt files yourself, or clone without them).
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, duration, load_env, need, require_ffmpeg  # noqa: E402
from cut_clip import cut  # noqa: E402

MIN_LEN, MAX_LEN, IDEAL = 15.0, 30.0, 25.0


def speech_runs(path):
    """[(start, end)] of speech between pauses of 0.3s or more."""
    mean = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000",
                           "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True).stderr
    found = re.findall(r"mean_volume: (-?[\d.]+) dB", mean)
    if not found:
        sys.exit(f"{path}: no audio track found.")
    floor = max(min(float(found[-1]) - 16.0, -30.0), -55.0)
    log = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000",
                          "-af", f"highpass=f=80,silencedetect=n={floor:.1f}dB:d=0.3", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end: (-?[\d.]+)", log)]
    total = duration(path)
    silences = list(zip(starts, ends + [total] * (len(starts) - len(ends))))
    runs, t = [], 0.0
    for a, b in silences:
        if a - t > 0.15:
            runs.append((max(t, 0.0), a))
        t = b
    if total - t > 0.15:
        runs.append((t, total))
    return runs


def candidates(path):
    """Windows of steady talking, best first: [(score, start, end)]."""
    runs = speech_runs(path)
    out = []
    for i, (start, _) in enumerate(runs):
        spoken, end, best = 0.0, None, None
        for a, b in runs[i:]:
            if end is not None and a - end > 1.2:  # a long pause: someone stopped talking, or a cut
                break
            if b - start > MAX_LEN:
                break
            spoken += b - a
            end = b
            length = end - start
            if length >= MIN_LEN:
                # Mostly speech, close to the ideal length, and early in the file.
                score = spoken / length - abs(length - IDEAL) / 60.0 - min(start, 600.0) / 3000.0
                if best is None or score > best[0]:
                    best = (score, start, end)
        if best and best[0] > 0.6:
            out.append(best)
    out.sort(reverse=True)
    picked = []
    for cand in out:
        if all(cand[2] <= p[1] - 1.0 or cand[1] >= p[2] + 1.0 for p in picked):
            picked.append(cand)
    return picked


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("sources", nargs="+", help="videos or recordings of you talking")
    p.add_argument("--clips", type=int, default=5, help="how many clips to keep (default 5)")
    p.add_argument("--out", default=str(ROOT / "me" / "voice"))
    p.add_argument("--no-transcribe", action="store_true", help="skip the transcripts and the second-speaker check")
    a = p.parse_args()
    require_ffmpeg()
    load_env()
    if not a.no_transcribe:
        need("FISH_API_KEY")
        from transcribe import transcribe

    for src in a.sources:
        if not Path(src).is_file():
            sys.exit(f"No such file: {src}")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    taken = [f for f in out.glob("clip-*.wav")]
    if taken:
        sys.exit(f"{out} already has {len(taken)} clip(s). Move or delete them first, or pass --out for a new folder.")

    # Take turns across the source files so the clips come from different recordings.
    queues = [[(src, *c) for c in candidates(src)] for src in a.sources]
    order = [q[i] for i in range(max((len(q) for q in queues), default=0)) for q in queues if i < len(q)]
    if not order:
        sys.exit("No stretch of 15 seconds or more of steady talking found. Try a recording with less music or "
                 "fewer cuts, or cut clips by hand with scripts/cut_clip.py.")

    kept, total = [], 0.0
    for src, _, start, end in order:
        if len(kept) >= a.clips:
            break
        n = len(kept) + 1
        clip = out / f"clip-{n}.wav"
        length = cut(src, clip, start + 0.05, end + 0.15)
        note = ""
        if not a.no_transcribe:
            result = transcribe(clip)
            words = len(result["text"].split())
            problem = None
            if result["speakers"] > 1:
                problem = "more than one person talks"
            elif any(e for e in result["events"] if any(k in e for k in ("music", "applause", "singing", "noise"))):
                problem = f"heard {', '.join(result['events'])}"
            elif words / length < 1.3:
                problem = "too little speech"
            if problem:
                clip.unlink()
                print(f"skipped {Path(src).name} {start:.1f}-{end:.1f}: {problem}")
                continue
            clip.with_suffix(".txt").write_text(result["text"] + "\n")
            note = f"  \"{result['text'][:70]}...\""
        kept.append(clip)
        total += length
        print(f"{clip}  {length:4.1f}s  "
              f"{Path(src).name} at {start:.1f}s{note}")

    if not kept:
        sys.exit("Every candidate was skipped. Use a recording where only you talk, with no music under it.")
    print(f"{len(kept)} clip(s), {total:.0f}s total in {out}.")
    if total < 45:
        print("That is on the short side. 1 to 2 minutes clones noticeably closer; add another recording if you have one.")
    print("Read the .txt files and fix any misheard names, then: "
          f"python3 scripts/clone_voice.py \"My AI Voice\" {out}/*.wav")


if __name__ == "__main__":
    main()
