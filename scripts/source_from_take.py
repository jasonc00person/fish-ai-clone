#!/usr/bin/env python3
"""Build a lip-sync source clip from an old take of you talking to the camera.

    python3 scripts/source_from_take.py my-old-video.mp4 outputs/my-video/01-hook \
        --ranges 53.3-57.5,92.0-97.8,114.1-118.7 --out outputs/my-video/01-hook/source.mp4

Lip-sync models keep the source clip's head motion and eyeline and only redo the
mouth, so pick stretches where you're looking straight into the lens. The ranges
play in order with jump cuts, and each cut lands on a pause in the new audio
(audio.wav + words.json from fish_tts.py), so the cuts fall between sentences.
The clip comes out exactly as long as the audio, since lip sync bills on the
clip's length, at 1080p with no audio.

Jump cuts show. If you can record (or already have) one continuous take of you
looking into the lens that is as long as the scene, use that instead: it needs
no stitching at all (scripts/chunk_scene.py --video take.mp4). This script is
for when all you have is footage where you only look at the lens now and then.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

MIN_PIECE = 1.0  # seconds; never cut sooner than this after the last cut


def duration(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 str(path)], capture_output=True, text=True, check=True).stdout.strip())


def main():
    p = argparse.ArgumentParser()
    p.add_argument("take")
    p.add_argument("scene_dir", help="folder from fish_tts.py (audio.wav + words.json)")
    p.add_argument("--ranges", required=True, help="lens-facing stretches in the take, e.g. 53.3-57.5,92.0-97.8")
    p.add_argument("--out", required=True)
    p.add_argument("--height", type=int, default=1080)
    p.add_argument("--loop", action="store_true", help="reuse the ranges from the top if they run out before the audio does")
    a = p.parse_args()

    scene = Path(a.scene_dir)
    total = duration(scene / "audio.wav")
    words = json.loads((scene / "words.json").read_text())
    pauses = [(x["end"] + y["start"]) / 2 for x, y in zip(words, words[1:]) if y["start"] - x["end"] >= 0.25]
    ranges = [tuple(float(v) for v in r.split("-")) for r in a.ranges.split(",")]

    pieces, at, i = [], 0.0, 0
    while at < total - 0.01:
        if i == len(ranges):
            if not a.loop:
                have = sum(e - s for s, e in ranges)
                sys.exit(f"The ranges add up to {have:.1f}s but the audio is {total:.1f}s. Add more lens-facing "
                         f"stretches, or pass --loop to reuse them from the top (the opening shot will repeat).")
            i = 0
        start, end = ranges[i]
        i += 1
        reach = at + (end - start)
        if reach >= total:
            cut = total
        else:
            fits = [x for x in pauses if at + MIN_PIECE <= x <= reach]
            cut = fits[-1] if fits else reach
        pieces.append((start, start + (cut - at)))
        at = cut

    chain = "".join(f"[0:v]trim={s:.3f}:{e:.3f},setpts=PTS-STARTPTS,scale=-2:{a.height},setsar=1[v{k}];"
                    for k, (s, e) in enumerate(pieces))
    graph = chain + "".join(f"[v{k}]" for k in range(len(pieces))) + f"concat=n={len(pieces)}:v=1:a=0[v]"
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", a.take, "-filter_complex", graph, "-map", "[v]",
                    "-t", f"{total:.3f}", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", a.out], check=True)
    for s, e in pieces:
        print(f"  take {s:7.2f} - {e:7.2f}  ({e - s:4.1f}s)")
    print(f"{a.out}: {duration(a.out):.2f}s for {total:.2f}s of audio, {len(pieces)} cuts")


if __name__ == "__main__":
    main()
