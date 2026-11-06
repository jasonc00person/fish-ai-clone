#!/usr/bin/env python3
"""Make a faceless clip: your cloned voice narrating over background footage.

    python3 scripts/fish_tts.py scenes/my-short/narration.txt outputs/my-short/narration
    python3 scripts/faceless.py outputs/my-short/narration footage/*.mp4 --out outputs/my-short/final.mp4 [--vertical]

The footage clips play in order, cropped to fill the frame, and loop if the
narration runs longer. Their own audio is dropped. Use footage you own or have
the rights to (your b-roll, stock, or clips you generated with Fish Audio's video
models). Writes final.mp4 plus final.srt captions from the word timestamps.
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from captions import caption_lines, to_srt  # noqa: E402

FPS = 30


def duration(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 str(path)], capture_output=True, text=True, check=True).stdout.strip())


def main():
    p = argparse.ArgumentParser()
    p.add_argument("narration_dir", help="folder from fish_tts.py (audio.wav + words.json)")
    p.add_argument("footage", nargs="+")
    p.add_argument("--out", required=True)
    p.add_argument("--vertical", action="store_true", help="1080x1920 for Shorts and Reels")
    a = p.parse_args()

    narr = Path(a.narration_dir)
    total = duration(narr / "audio.wav")
    w, h = (1080, 1920) if a.vertical else (1920, 1080)

    clips = [(f, duration(f)) for f in a.footage]
    loops = math.ceil(total / sum(d for _, d in clips))
    inputs = [f for _ in range(loops) for f, _ in clips]

    args, chain = [], []
    for i, f in enumerate(inputs):
        args += ["-i", str(f)]
        chain.append(f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={FPS},setsar=1[v{i}]")
    n = len(inputs)
    graph = ";".join(chain) + ";" + "".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]"

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args, "-i", str(narr / "audio.wav"), "-filter_complex", graph,
                    "-map", "[v]", "-map", f"{n}:a", "-t", f"{total:.3f}",
                    "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out)], check=True)
    out.with_suffix(".srt").write_text(to_srt(caption_lines(json.loads((narr / "words.json").read_text()))))
    print(f"{out} ({total:.1f}s, {w}x{h}) + {out.with_suffix('.srt').name}")


if __name__ == "__main__":
    main()
