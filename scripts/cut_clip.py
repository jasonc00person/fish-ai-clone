#!/usr/bin/env python3
"""Cut a clean voice clip out of any video or audio file of you talking.

    python3 scripts/cut_clip.py my-video.mp4 me/voice/clip-1.wav --start 12.5 --end 38

Mono, 48 kHz, rumble filtered, leveled. Pick stretches where only you talk:
no music, no screen audio, no other people. Write what you say in the clip
into a .txt with the same name (me/voice/clip-1.txt) so clone_voice.py can
send the transcript with it.
"""
import argparse
import subprocess
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("src")
    p.add_argument("out")
    p.add_argument("--start", type=float, default=0.0)
    p.add_argument("--end", type=float, default=None)
    args = p.parse_args()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    trim = ["-ss", str(args.start)] + (["-to", str(args.end)] if args.end else [])
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", *trim, "-i", args.src, "-vn",
         "-af", "highpass=f=70,loudnorm=I=-18:TP=-1.5:LRA=11", "-ar", "48000", "-ac", "1", args.out],
        check=True,
    )
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", args.out],
                         capture_output=True, text=True, check=True).stdout.strip()
    print(f"{args.out}: {float(dur):.1f}s")


if __name__ == "__main__":
    main()
