#!/usr/bin/env python3
"""Cut a rendered scene into pieces a video model will take, at sentence breaks.

    # Photo avatar: one job takes about 59s of audio, so a longer scene is split
    python3 scripts/chunk_scene.py outputs/my-video/01-main

    # Lip sync on a real take: short chunks render reliably, and each chunk gets
    # its matching stretch of footage, frame for frame
    python3 scripts/chunk_scene.py outputs/my-video/01-main --max 20 \
        --video me/take.mp4 --video-start 14.7

The word timestamps say where every sentence ends and how long each pause is, so
every cut lands in a pause with the mouth closed. Writes into <scene>/chunks/:

    01.wav, 02.wav, ...   the audio for each job (upload these as sourceAudio)
    01-source.mp4, ...    with --video: the footage for each job (sourceVideo)
    chunks.json           where each chunk sits on the scene's timeline

Render each chunk, save the results as chunks/01.mp4, chunks/02.mp4, ... and
assemble.py joins them back into one clip under the scene's clean audio.

With --video, the take plays continuously: chunk 2 starts on the frame after
chunk 1 ends, so the joins are invisible. The script prints where the next
scene should start (--video-start) to keep that going across scenes. Footage is
re-encoded to about 14 Mbps because Fish Audio rejects very large 4K uploads.
"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from align import align  # noqa: E402
from common import duration, ffmpeg, require_ffmpeg, video_info  # noqa: E402

MIN_GAP = 0.12  # seconds of silence a cut needs


def scene_words(scene):
    """(audio path, words on that audio's timeline, script text). Dialogue scenes use the speaker 0 track."""
    words = json.loads((scene / "words.json").read_text())
    text = (scene / "scene.txt").read_text() if (scene / "scene.txt").is_file() else ""
    aligned = align(text, words)
    if (scene / "pieces.json").exists():
        pieces = json.loads((scene / "pieces.json").read_text())
        moved = []
        for w in aligned:
            for p in pieces:
                if p["start"] - 0.01 <= w["start"] < p["end"]:
                    shift = p["at"] - p["start"]
                    moved.append({**w, "start": w["start"] + shift, "end": w["end"] + shift})
                    break
        return scene / "speaker0-only.wav", moved, text
    return scene / "audio.wav", aligned, text


def cut_points(words, total, longest):
    """Times to cut at so no chunk runs past `longest`, preferring sentence ends, then the longest pauses."""
    n = math.ceil(total / longest)
    if n <= 1:
        return []
    gaps = [{"t": (a["end"] + b["start"]) / 2, "len": b["start"] - a["end"], "sentence": a.get("sentence_end", False)}
            for a, b in zip(words, words[1:]) if b["start"] - a["end"] >= MIN_GAP]
    cuts, prev = [], 0.0
    for k in range(1, n + 8):
        remaining = total - prev
        if remaining <= longest:
            break
        left = math.ceil(remaining / longest)
        ideal = prev + remaining / left
        lo, hi = prev + min(3.0, longest / 4), prev + longest
        fits = [g for g in gaps if lo <= g["t"] <= hi and total - g["t"] <= (left - 1) * longest]
        if fits:
            span = max(remaining / left, 1.0)
            cut = max(fits, key=lambda g: (1.0 if g["sentence"] else 0.0) + min(g["len"], 1.0)
                      - 0.8 * abs(g["t"] - ideal) / span)["t"]
        else:
            cut = min(ideal, hi)
            print(f"No pause to cut in between {lo:.1f}s and {hi:.1f}s; cutting at {cut:.1f}s mid-phrase.", file=sys.stderr)
        cuts.append(cut)
        prev = cut
    return cuts


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("scene_dir", help="folder from fish_tts.py (audio.wav + words.json)")
    p.add_argument("--max", type=float, default=55.0,
                   help="longest chunk in seconds (default 55 for photo avatars; use 20 for lip sync on 4K footage)")
    p.add_argument("--video", help="a continuous take of you looking into the lens, to cut matching footage from")
    p.add_argument("--video-start", type=float, default=0.0, help="seconds into the take where this scene starts")
    p.add_argument("--height", type=int, default=None, help="scale the footage to this height (default: keep the take's size)")
    a = p.parse_args()
    require_ffmpeg()

    scene = Path(a.scene_dir)
    audio, words, _ = scene_words(scene)
    total = duration(audio)
    cuts = cut_points(words, total, a.max)
    bounds = [0.0, *cuts, total]

    out = scene / "chunks"
    out.mkdir(exist_ok=True)
    for old in list(out.glob("[0-9][0-9].wav")) + list(out.glob("[0-9][0-9]-source.mp4")) + list(out.glob("joined.mp4")):
        old.unlink()
    stale = sorted(out.glob("[0-9][0-9].mp4"))
    if stale:
        # Renders of the previous cut no longer match these chunks. Keep them, out of the way.
        (out / "old").mkdir(exist_ok=True)
        for clip in stale:
            clip.replace(out / "old" / clip.name)
        print(f"Moved {len(stale)} earlier render(s) to {out / 'old'}: they were cut for the previous chunks.")

    rate = fps = None
    if a.video:
        _, _, fps, rate = video_info(a.video)
        take_len = duration(a.video)
        if a.video_start + total > take_len + 0.05:
            sys.exit(f"The take is {take_len:.1f}s long but this scene needs {a.video_start:.1f}s to "
                     f"{a.video_start + total:.1f}s of it. Start earlier or record a longer take.")
        # Snap every boundary to a frame so audio and footage stay the same length, chunk after chunk.
        first = round(a.video_start * rate)
        frames = [round(b * rate) for b in bounds]
        frames[-1] = math.ceil(total * rate)
        bounds = [f / rate for f in frames]

    chunks = []
    for i, (start, end) in enumerate(zip(bounds, bounds[1:]), 1):
        name = f"{i:02d}"
        ffmpeg("-i", audio, "-af", f"atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS,apad",
               "-t", f"{end - start:.6f}", "-c:a", "pcm_s16le", out / f"{name}.wav")
        chunk = {"n": i, "start": round(start, 4), "end": round(end, 4), "audio": f"chunks/{name}.wav",
                 "video": f"chunks/{name}.mp4"}
        if a.video:
            count = frames[i] - frames[i - 1]
            scale = ["-vf", f"scale=-2:{a.height}"] if a.height else []
            ffmpeg("-ss", f"{(first + frames[i - 1]) / rate:.6f}", "-i", a.video, "-frames:v", str(count), "-an", *scale,
                   "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-maxrate", "14M", "-bufsize", "28M",
                   "-pix_fmt", "yuv420p", "-r", fps, out / f"{name}-source.mp4")
            chunk.update(source=f"chunks/{name}-source.mp4", frames=count,
                         take_start=round((first + frames[i - 1]) / rate, 4))
        chunks.append(chunk)
        size = f", {(out / f'{name}-source.mp4').stat().st_size / 1e6:.0f} MB of footage" if a.video else ""
        print(f"chunk {name}: {start:6.2f} - {end:6.2f}  ({end - start:.1f}s{size})")

    (scene / "chunks.json").write_text(json.dumps({"audio": audio.name, "fps": fps, "chunks": chunks}, indent=1))
    print(f"{len(chunks)} chunk(s) in {out}. Render each one and save it as chunks/NN.mp4, then run assemble.py.")
    if a.video:
        print(f"Next scene on the same take: --video-start {a.video_start + bounds[-1]:.3f}")


if __name__ == "__main__":
    main()
