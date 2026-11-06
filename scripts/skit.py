#!/usr/bin/env python3
"""Turn a dialogue scene into a cartoon skit: one shot per line, each lip-synced on its own keyframe.

    # 1. One audio clip per line (after fish_tts.py and split_speakers.py on the scene)
    python3 scripts/skit.py split outputs/my-video/02-skit

    # 2. For each shots/shotNN.wav: generate a keyframe image, then a talking-avatar
    #    video (keyframe + shotNN.wav) with the Fish Audio MCP. Save it as shots/shotNN.mp4.

    # 3. Cut the shots together over the original audio
    python3 scripts/skit.py assemble outputs/my-video/02-skit

split writes shots/shotNN.wav, one per turn in turns.json, cut from audio.wav so each
shot starts and ends where its line's turn does. assemble trims each shotNN.mp4 to its
turn's exact length, cuts them together in order and lays the original audio.wav under
the whole thing, so the timing matches the voice track to the frame. Output: skit.mp4.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

FPS = "24000/1001"


def run(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def split(scene):
    turns = json.loads((scene / "turns.json").read_text())
    (scene / "shots").mkdir(exist_ok=True)
    for i, t in enumerate(turns, 1):
        out = scene / "shots" / f"shot{i:02d}.wav"
        run("-i", str(scene / "audio.wav"), "-ss", f"{t['region_start']:.3f}", "-to", f"{t['region_end']:.3f}",
            "-c:a", "pcm_s16le", str(out))
        print(f"{out}  {t['region_end'] - t['region_start']:5.2f}s  speaker {t['speaker']}: {t['text'][:60]}")


def assemble(scene, out, width, height):
    turns = json.loads((scene / "turns.json").read_text())
    shots = [scene / "shots" / f"shot{i:02d}.mp4" for i in range(1, len(turns) + 1)]
    missing = [s.name for s in shots if not s.exists()]
    if missing:
        sys.exit(f"Missing in {scene / 'shots'}: {', '.join(missing)}")
    args, chain = [], ""
    rate = 24000 / 1001
    for k, (s, t) in enumerate(zip(shots, turns)):
        # Cut on the frame nearest each turn's start and end on the scene's timeline, so rounding never adds up.
        frames = round(t["region_end"] * rate) - round(t["region_start"] * rate)
        args += ["-i", str(s)]
        # Fill the frame, hold the last frame if a shot runs short, then cut to the turn's length.
        chain += (f"[{k}:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
                  f"setsar=1,fps={FPS},tpad=stop_mode=clone:stop_duration=1,trim=end_frame={frames},setpts=PTS-STARTPTS[v{k}];")
    graph = chain + "".join(f"[v{k}]" for k in range(len(shots))) + f"concat=n={len(shots)}:v=1:a=0[v]"
    run(*args, "-i", str(scene / "audio.wav"), "-filter_complex", graph, "-map", "[v]", "-map", f"{len(shots)}:a",
        "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-shortest", "-movflags", "+faststart", str(out))
    print(f"{out}: {len(shots)} shots")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    ps = sub.add_parser("split")
    ps.add_argument("scene_dir")
    pa = sub.add_parser("assemble")
    pa.add_argument("scene_dir")
    pa.add_argument("--out", help="default: <scene_dir>/skit.mp4")
    pa.add_argument("--size", default="1920x1080")
    a = p.parse_args()
    scene = Path(a.scene_dir)
    if a.cmd == "split":
        split(scene)
    else:
        w, h = (int(v) for v in a.size.split("x"))
        assemble(scene, Path(a.out) if a.out else scene / "skit.mp4", w, h)


if __name__ == "__main__":
    main()
