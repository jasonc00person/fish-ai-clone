#!/usr/bin/env python3
"""Put the finished avatar clips together into one video plus captions.

    python3 scripts/assemble.py outputs/my-video

Every scene folder in outputs/my-video needs audio.wav + words.json (from
fish_tts.py) and avatar.mp4 (the avatar render you downloaded). For each scene:

- one speaker: the avatar video with the clean audio.wav laid back on top
- dialogue (has pieces.json from split_speakers.py): your avatar on your lines,
  a waveform card on the other voice's lines, full two-voice audio underneath

Writes scene.mp4 in each folder, then final.mp4 + final.srt in the project folder.
Captions come out as a separate .srt so you can style them in your editor or
upload them to YouTube.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from captions import caption_lines, to_srt  # noqa: E402

FPS = 30
CARD_BG, WAVE = "0x141414", "0xD97757"
ENCODE = ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart"]


def probe(path, entries, stream="v:0"):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", stream, "-show_entries", entries,
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True).stdout
    return out.strip().split("\n")[0].split(",")


def duration(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 str(path)], capture_output=True, text=True, check=True).stdout.strip())


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def single(scene, w, h):
    ffmpeg("-i", str(scene / "avatar.mp4"), "-i", str(scene / "audio.wav"),
           "-filter_complex", f"[0:v]fps={FPS},scale={w}:{h}:force_original_aspect_ratio=decrease,"
                              f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1[v]",
           "-map", "[v]", "-map", "1:a", "-shortest", *ENCODE, str(scene / "scene.mp4"))


def dialogue(scene, w, h):
    pieces = json.loads((scene / "pieces.json").read_text())
    dur = duration(scene / "audio.wav")
    n = len(pieces)
    f = [f"color=c={CARD_BG}:s={w}x{h}:r={FPS}:d={dur:.3f}[bg]",
         f"[1:a]showwaves=s={w}x{h // 4}:mode=cline:draw=full:rate={FPS}:colors={WAVE},format=yuva420p[wave]",
         "[bg][wave]overlay=0:(H-h)/2:shortest=1[o_]",
         f"[0:v]fps={FPS},scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
         f"setsar=1,split={n}" + "".join(f"[s{i}]" for i in range(n))]
    prev = "o_"
    for i, p in enumerate(pieces):
        length = p["end"] - p["start"]
        f.append(f"[s{i}]trim=start={p['at']:.3f}:end={p['at'] + length:.3f},"
                 f"setpts=PTS-STARTPTS+{p['start']:.3f}/TB[p{i}]")
        f.append(f"[{prev}][p{i}]overlay=eof_action=pass:enable='between(t,{p['start']:.3f},{p['end']:.3f})'[o{i}]")
        prev = f"o{i}"
    ffmpeg("-i", str(scene / "avatar.mp4"), "-i", str(scene / "audio.wav"),
           "-filter_complex", ";".join(f), "-map", f"[{prev}]", "-map", "1:a", "-t", f"{dur:.3f}",
           *ENCODE, str(scene / "scene.mp4"))


def main():
    project = Path(sys.argv[1])
    scenes = sorted(d for d in project.iterdir() if (d / "audio.wav").exists())
    missing = [d.name for d in scenes if not (d / "avatar.mp4").exists()]
    if not scenes or missing:
        sys.exit(f"No avatar.mp4 yet in: {', '.join(missing) or project}")

    w, h = (int(x) for x in probe(scenes[0] / "avatar.mp4", "stream=width,height"))
    captions, offset = [], 0.0
    for scene in scenes:
        (dialogue if (scene / "pieces.json").exists() else single)(scene, w, h)
        captions += caption_lines(json.loads((scene / "words.json").read_text()), offset)
        offset += duration(scene / "scene.mp4")
        print(f"{scene.name}: scene.mp4 done")

    concat = project / "concat.txt"
    concat.write_text("".join(f"file '{(s / 'scene.mp4').resolve()}'\n" for s in scenes))
    ffmpeg("-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(project / "final.mp4"))
    concat.unlink()
    (project / "final.srt").write_text(to_srt(captions))
    print(f"{project / 'final.mp4'} ({offset:.1f}s, {w}x{h}) + final.srt")


if __name__ == "__main__":
    main()
