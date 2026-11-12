#!/usr/bin/env python3
"""Cut a clean voice clip out of any video or audio file of you talking.

    python3 scripts/cut_clip.py my-video.mp4 me/voice/clip-1.wav --start 12.5 --end 38

Mono, 48 kHz, rumble filtered, leveled with plain gain (no compression, so the
clone hears your real dynamics). Pick stretches where only you talk: no music,
no screen audio, no other people. Write what you say in the clip into a .txt
with the same name (me/voice/clip-1.txt) so clone_voice.py can send the
transcript with it. voice_samples.py does all of this for you.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import duration, ffmpeg, level_gain, require_ffmpeg  # noqa: E402


def cut(src, out, start=0.0, end=None, target_lufs=-18.0):
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    trim = ["-ss", str(start)] + (["-to", str(end)] if end else [])
    gain = level_gain([*trim, "-i", src, "-vn"], target_lufs, ceiling_db=-1.5)
    ffmpeg(*trim, "-i", src, "-vn", "-af", f"highpass=f=70,volume={gain:.2f}dB", "-ar", "48000", "-ac", "1", out)
    return duration(out)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("src")
    p.add_argument("out")
    p.add_argument("--start", type=float, default=0.0)
    p.add_argument("--end", type=float, default=None)
    a = p.parse_args()
    require_ffmpeg()
    if not Path(a.src).is_file():
        sys.exit(f"No such file: {a.src}")
    print(f"{a.out}: {cut(a.src, a.out, a.start, a.end):.1f}s")


if __name__ == "__main__":
    main()
