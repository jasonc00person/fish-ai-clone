#!/usr/bin/env python3
"""Tighten talking clips: trim the dead air, shrink the pauses, level the audio, cut them together.

    python3 scripts/tighten.py shots/shot01.mp4 shots/shot02.mp4 ... --out outputs/my-skit/skit.mp4
    python3 scripts/tighten.py clip.mp4 --out clip-tight.mp4 --speed 1.0 --keep-pause 0.2

Video models that generate their own speech talk slowly (about 140 words a
minute), leave long pauses inside and between lines, and return every clip at a
different loudness. This fixes all three in post, which is cheaper and more
reliable than re-prompting:

- each clip is trimmed to its first and last word
- pauses longer than --max-pause are cut down to --keep-pause (small jump cuts,
  which read as normal editing on a locked-off shot)
- each clip is leveled to the same loudness with plain gain
- the result plays at --speed with the pitch kept (1.15 lands near 180 words a minute)

Clips are cut together in the order given, at the size and frame rate of the first.
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import duration, ffmpeg, level_gain, require_ffmpeg, video_info  # noqa: E402

HEAD, TAIL = 0.05, 0.08  # seconds kept before the first word and after the last


def speech(path):
    """[(start, end)] of speech in a clip. Blips under 0.1s are dropped: they would become 2-frame jump cuts."""
    total = duration(path)
    mean = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path), "-vn", "-af", "volumedetect",
                           "-f", "null", "-"], capture_output=True, text=True).stderr
    found = re.findall(r"mean_volume: (-?[\d.]+) dB", mean)
    if not found:
        sys.exit(f"{path}: no audio track.")
    floor = max(min(float(found[-1]) - 14.0, -30.0), -55.0)
    log = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path), "-vn",
                          "-af", f"silencedetect=n={floor:.1f}dB:d=0.18", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end: (-?[\d.]+)", log)]
    segs, t = [], 0.0
    for a, b in zip(starts, ends + [total] * (len(starts) - len(ends))):
        if a > t + 0.01:
            segs.append((t, a))
        t = max(t, b)
    if t < total - 0.01:
        segs.append((t, total))
    return [s for s in segs if s[1] - s[0] >= 0.1], total


def keeps(path, max_pause, keep_pause):
    """The stretches of a clip to keep, with long pauses shortened."""
    segs, total = speech(path)
    if not segs:
        return [[0.0, total]]
    out = [[max(0.0, segs[0][0] - HEAD), segs[0][1]]]
    for start, end in segs[1:]:
        gap = start - out[-1][1]
        if gap <= max(max_pause, keep_pause):
            out[-1][1] = end
        else:
            out[-1][1] += keep_pause / 2
            out.append([start - keep_pause / 2, end])
    out[-1][1] = min(total, out[-1][1] + TAIL)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("clips", nargs="+", help="talking clips with their own audio, in playing order")
    p.add_argument("--out", required=True)
    p.add_argument("--speed", type=float, default=1.15, help="playback speed, pitch kept (default 1.15; 1.0 leaves it alone)")
    p.add_argument("--max-pause", type=float, default=0.26, help="pauses longer than this get shortened (seconds)")
    p.add_argument("--keep-pause", type=float, default=0.12, help="what a shortened pause is cut down to (seconds)")
    p.add_argument("--lufs", type=float, default=-16.0, help="loudness every clip is leveled to")
    a = p.parse_args()
    require_ffmpeg()
    if not 0.5 <= a.speed <= 2.0:
        sys.exit("--speed must be between 0.5 and 2.0")
    for c in a.clips:
        if not Path(c).is_file():
            sys.exit(f"No such file: {c}")

    w, h, fps, _ = video_info(a.clips[0])
    w, h = w - w % 2, h - h % 2
    before = after = 0.0
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for i, clip in enumerate(a.clips):
            segs = keeps(clip, a.max_pause, a.keep_pause)
            gain = level_gain(["-i", clip], a.lufs)
            graph = ""
            for k, (s, e) in enumerate(segs):
                graph += (f"[0:v]trim={s:.3f}:{e:.3f},setpts=PTS-STARTPTS,fps={fps},"
                          f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1[v{k}];"
                          f"[0:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS,volume={gain:.2f}dB,"
                          f"aformat=sample_rates=48000:channel_layouts=mono,afade=t=in:d=0.008,"
                          f"afade=t=out:st={max(e - s - 0.008, 0):.3f}:d=0.008[a{k}];")
            graph += "".join(f"[v{k}][a{k}]" for k in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=1[v][a]"
            part = Path(tmp) / f"{i:03d}.mov"
            ffmpeg("-i", clip, "-filter_complex", graph, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "14",
                   "-preset", "fast", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", part)
            parts.append(part)
            kept = sum(e - s for s, e in segs)
            before += duration(clip)
            after += kept
            print(f"{Path(clip).name}: {duration(clip):.2f}s -> {kept:.2f}s, {len(segs) - 1} pause(s) shortened, {gain:+.1f} dB")

        listing = Path(tmp) / "list.txt"
        listing.write_text("".join("file '" + str(p).replace("'", "'\\''") + "'\n" for p in parts))
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        speed = (["-filter_complex", f"[0:v]setpts=PTS/{a.speed},fps={fps}[v];[0:a]atempo={a.speed}[a]",
                  "-map", "[v]", "-map", "[a]"] if abs(a.speed - 1.0) > 1e-3 else [])
        ffmpeg("-f", "concat", "-safe", "0", "-i", listing, *speed, "-c:v", "libx264", "-crf", "17", "-preset", "medium",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-movflags", "+faststart", out)
    print(f"{a.out}: {before:.1f}s -> {duration(a.out):.1f}s ({len(a.clips)} clip(s), speed {a.speed}x)")


if __name__ == "__main__":
    main()
