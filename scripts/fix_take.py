#!/usr/bin/env python3
"""Fix a flubbed line in a real take with your AI avatar (or a lip sync on the real footage).

    # 1. Cut the flubbed stretch and voice the corrected line
    python3 scripts/fix_take.py prepare take.mp4 --start 83.2 --end 87.9 \
        --text "[casual] It took me thirty minutes." --out outputs/fix-thirty-minutes

    # 2. Render it with the Fish Audio MCP and save the result as synced.mp4:
    #    avatar route:    frame.jpg + line.wav  (avatar_audio model)
    #    lip-sync route:  clip.mp4  + line.wav  (video_audio model)

    # 3. Put it back
    python3 scripts/fix_take.py splice take.mp4 outputs/fix-thirty-minutes

prepare writes line.wav (the new line, matched to the take's loudness and padded to
the stretch being replaced), frame.jpg (a still from the same shot, so the avatar
matches the take's framing and light), clip.mp4 (that stretch of footage, no audio),
original.mp4 (the flubbed version, for comparison) and fix.json. Both routes bill
on length, so the stretch is only as long as it needs to be.

splice writes fixed.mp4 (the whole take with the line replaced) and compare.mp4
(the original stretch, then the fixed one). The take's own room tone is laid
under the new line, so the sound doesn't drop into dead silence at the cut.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import require_ffmpeg  # noqa: E402
ENCODE = ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart"]


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def duration(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 str(path)], capture_output=True, text=True, check=True).stdout.strip())


def video_info(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip().split(",")
    num, den = out[2].split("/")
    return int(out[0]), int(out[1]), round(int(num) / int(den), 3)


def loudness(args):
    stats = subprocess.run(["ffmpeg", "-hide_banner", *args, "-af", "ebur128", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", stats)[-1])


def room_tone(take, start, end, out):
    """Save about half a second of the take's quietest nearby audio (the room with nobody talking)."""
    a, b = max(0.0, start - 30), min(duration(take), end + 30)
    mean = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-ss", str(a), "-to", str(b), "-i", take, "-vn",
                           "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True).stderr
    level = re.findall(r"mean_volume: (-?[\d.]+) dB", mean)
    if not level:
        return False
    floor = max(min(float(level[-1]) - 14.0, -30.0), -60.0)
    log = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-ss", str(a), "-to", str(b), "-i", take, "-vn",
                          "-af", f"silencedetect=n={floor:.1f}dB:d=0.4", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    gaps = sorted(((float(e) - float(s), float(s)) for s, e in
                   zip(re.findall(r"silence_start: (-?[\d.]+)", log), re.findall(r"silence_end: (-?[\d.]+)", log))),
                  reverse=True)
    if not gaps:
        return False
    length, at = gaps[0]
    # Stay clear of the words on either side of the pause.
    ffmpeg("-ss", f"{a + at + 0.1:.3f}", "-t", f"{max(length - 0.2, 0.2):.3f}", "-i", take, "-vn",
           "-ar", "48000", "-ac", "1", str(out))
    return True


def prepare(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "line.txt").write_text(a.text.strip() + "\n")
    takes = ["--takes", str(a.takes)] if a.takes > 1 else []
    subprocess.run([sys.executable, str(HERE / "fish_tts.py"), str(out / "line.txt"), str(out / "tts"), *takes], check=True)

    line_len = duration(out / "tts" / "audio.wav")
    start = a.start
    end = max(a.end, start + line_len + 0.3)
    take_len = duration(a.take)
    if end > take_len:
        if start + line_len > take_len:
            sys.exit(f"The new line is {line_len:.1f}s but only {take_len - start:.1f}s of the take is left after "
                     f"--start. Shorten the line or start earlier.")
        end = take_len
    length = end - start
    if end > a.end + 0.05:
        print(f"NOTE: the new line runs {line_len:.1f}s, longer than the {a.end - start:.1f}s being replaced, so the fix "
              f"now ends at {end:.2f}s and covers whatever is said until then. Shorten the line, or check that "
              f"nothing you need is spoken between {a.end:.2f}s and {end:.2f}s.", file=sys.stderr)

    # Match the take's loudness so the fix doesn't jump out, and pad to the clip length.
    target = loudness(["-ss", str(start), "-to", str(a.end), "-i", a.take])
    current = loudness(["-i", str(out / "tts" / "audio.wav")])
    ffmpeg("-i", str(out / "tts" / "audio.wav"), "-af", f"volume={target - current:.2f}dB,apad",
           "-t", f"{length:.3f}", "-ar", "48000", "-ac", "1", str(out / "line.wav"))

    # Capped bitrate: Fish Audio rejects very large 4K uploads.
    ffmpeg("-ss", str(start), "-to", str(end), "-i", a.take, "-an", "-c:v", "libx264", "-crf", "16",
           "-maxrate", "14M", "-bufsize", "28M", "-pix_fmt", "yuv420p", str(out / "clip.mp4"))
    room_tone(a.take, start, end, out / "room.wav")
    frame_at = a.frame_at if a.frame_at is not None else start
    ffmpeg("-ss", str(frame_at), "-i", a.take, "-frames:v", "1", "-q:v", "2", str(out / "frame.jpg"))
    ffmpeg("-ss", str(start), "-to", str(end), "-i", a.take, *ENCODE, str(out / "original.mp4"))
    (out / "fix.json").write_text(json.dumps({"take": str(Path(a.take).resolve()), "start": start, "end": end,
                                              "line_sec": round(line_len, 2), "clip_sec": round(length, 2)}, indent=1))
    print(f"line.wav, frame.jpg and clip.mp4 ready ({length:.1f}s; both routes bill on this length).")
    print("Next: avatar (frame.jpg + line.wav) or lip sync (clip.mp4 + line.wav), save it as synced.mp4, run splice.")


def splice(a):
    out = Path(a.out_dir)
    fix = json.loads((out / "fix.json").read_text())
    if not (out / "synced.mp4").exists():
        sys.exit(f"No synced.mp4 in {out} yet. Download the lip-sync result there first.")
    w, h, fps = video_info(a.take)
    norm = f"fps={fps},scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    s, e, length = fix["start"], fix["end"], fix["end"] - fix["start"]

    tail = duration(a.take) - e > 0.05  # is there any take left after the fix?

    # The new line over the take's room tone, so the background sound carries through the fix.
    line = out / "line.wav"
    if (out / "room.wav").exists():
        ffmpeg("-i", str(out / "line.wav"), "-stream_loop", "-1", "-i", str(out / "room.wav"), "-filter_complex",
               "[1:a]aformat=sample_rates=48000:channel_layouts=mono[r];[0:a][r]amix=inputs=2:normalize=0:duration=first[a]",
               "-map", "[a]", "-t", f"{length:.3f}", str(out / "line-room.wav"))
        line = out / "line-room.wav"

    ffmpeg("-i", a.take, "-i", str(out / "synced.mp4"), "-i", str(line), "-filter_complex",
           f"[0:v]trim=0:{s},setpts=PTS-STARTPTS,{norm}[v0];[0:a]atrim=0:{s},asetpts=PTS-STARTPTS[a0];"
           f"[1:v]trim=0:{length},setpts=PTS-STARTPTS,{norm}[v1];[2:a]aformat=sample_rates=48000:channel_layouts=stereo,"
           f"atrim=0:{length},asetpts=PTS-STARTPTS[a1];"
           + (f"[0:v]trim=start={e},setpts=PTS-STARTPTS,{norm}[v2];[0:a]atrim=start={e},asetpts=PTS-STARTPTS[a2];"
              "[a2]aformat=sample_rates=48000:channel_layouts=stereo[a2s];" if tail else "")
           + "[a0]aformat=sample_rates=48000:channel_layouts=stereo[a0s];"
           + ("[v0][a0s][v1][a1][v2][a2s]concat=n=3:v=1:a=1[v][aout]" if tail else "[v0][a0s][v1][a1]concat=n=2:v=1:a=1[v][aout]"),
           "-map", "[v]", "-map", "[aout]", *ENCODE, str(out / "fixed.mp4"))

    ffmpeg("-i", str(out / "original.mp4"), "-i", str(out / "synced.mp4"), "-i", str(line),
           "-filter_complex",
           f"[0:v]{norm}[v0];[0:a]aformat=sample_rates=48000:channel_layouts=stereo[a0];"
           f"color=c=black:s={w}x{h}:r={fps}:d=0.6,setsar=1[g];anullsrc=r=48000:cl=stereo,atrim=0:0.6[ga];"
           f"[1:v]trim=0:{length},setpts=PTS-STARTPTS,{norm}[v1];[2:a]aformat=sample_rates=48000:channel_layouts=stereo[a1];"
           "[v0][a0][g][ga][v1][a1]concat=n=3:v=1:a=1[v][aout]",
           "-map", "[v]", "-map", "[aout]", *ENCODE, str(out / "compare.mp4"))
    print(f"{out / 'fixed.mp4'} ({duration(out / 'fixed.mp4'):.1f}s) + {out / 'compare.mp4'} (before, then after)")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("prepare")
    pp.add_argument("take")
    pp.add_argument("--start", type=float, required=True, help="seconds into the take where the flubbed line starts")
    pp.add_argument("--end", type=float, required=True, help="seconds where it ends")
    pp.add_argument("--text", required=True, help="the corrected line, Drama 3 tags allowed")
    pp.add_argument("--frame-at", type=float, default=None,
                    help="seconds into the take for the avatar still (pick a moment with the mouth closed); defaults to --start")
    pp.add_argument("--takes", type=int, default=3, help="render this many takes of the line and keep the best (default 3)")
    pp.add_argument("--out", required=True)
    ps = sub.add_parser("splice")
    ps.add_argument("take")
    ps.add_argument("out_dir")
    a = p.parse_args()
    require_ffmpeg()
    if not Path(a.take).is_file():
        sys.exit(f"No such file: {a.take}")
    if a.cmd == "prepare" and a.end <= a.start:
        sys.exit("--end must be after --start.")
    prepare(a) if a.cmd == "prepare" else splice(a)


if __name__ == "__main__":
    main()
