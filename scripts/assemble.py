#!/usr/bin/env python3
"""Put the finished avatar clips together into one video plus captions.

    python3 scripts/assemble.py outputs/my-video

Every scene folder in outputs/my-video needs audio.wav + words.json (from
fish_tts.py) and the rendered face: avatar.mp4, or chunks/01.mp4, 02.mp4, ...
if the scene was split with chunk_scene.py (chunk renders are rejoined on every
run, so re-rendering one chunk and assembling again just works). For each scene:

- one speaker: the face video with the clean audio.wav laid back on top
- dialogue (has pieces.json from split_speakers.py): your face on your lines,
  a waveform card on the other voice's lines, full two-voice audio underneath

Writes scene.mp4 in each folder, then final.mp4 + final.srt in the project folder.
Every scene comes out exactly as long as its audio, at the frame rate the face
video was rendered at. Captions come out as a separate .srt so you can style
them in your editor or upload them to YouTube.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from captions import caption_lines, scene_text, to_srt  # noqa: E402
from common import duration, ffmpeg, require_ffmpeg, video_info  # noqa: E402

CARD_BG, WAVE = "0x141414", "0xD97757"
ENCODE = ["-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart"]


def fit(w, h, fps):
    return f"fps={fps},scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1"


def join_chunks(scene, w, h, fps, rate):
    """chunks/NN.mp4 -> chunks/joined.mp4, each cut to its exact frame count so nothing drifts.

    Rebuilt on every run, so a chunk you rendered again always makes it into the final video.
    """
    plan = json.loads((scene / "chunks.json").read_text())["chunks"]
    clips = [scene / c["video"] for c in plan]
    missing = [c.name for c in clips if not c.exists()]
    if missing:
        sys.exit(f"{scene.name}: still waiting on {', '.join(missing)} in {scene / 'chunks'}")
    args, graph = [], ""
    for k, (clip, c) in enumerate(zip(clips, plan)):
        frames = c.get("frames") or round(c["end"] * rate) - round(c["start"] * rate)
        args += ["-i", clip]
        graph += (f"[{k}:v]{fit(w, h, fps)},tpad=stop_mode=clone:stop_duration=2,"
                  f"trim=end_frame={frames},setpts=PTS-STARTPTS[v{k}];")
    graph += "".join(f"[v{k}]" for k in range(len(clips))) + f"concat=n={len(clips)}:v=1:a=0[v]"
    joined = scene / "chunks" / "joined.mp4"
    ffmpeg(*args, "-filter_complex", graph, "-map", "[v]", "-c:v", "libx264", "-crf", "14", "-preset", "medium",
           "-pix_fmt", "yuv420p", joined)
    return joined


def check_length(scene, face, audio_name):
    have, audio = duration(face), duration(scene / audio_name)
    if have < audio - 1.0:
        print(f"WARNING {scene.name}: the face video is {have:.1f}s but its audio is {audio:.1f}s. "
              f"Is this the right render?", file=sys.stderr)


def single(scene, face, w, h, fps):
    dur = duration(scene / "audio.wav")
    check_length(scene, face, "audio.wav")
    # Hold the last frame if the render came back a few frames short, then cut to the audio's exact length.
    ffmpeg("-i", face, "-i", scene / "audio.wav",
           "-filter_complex", f"[0:v]{fit(w, h, fps)},tpad=stop_mode=clone:stop_duration=3[v];[1:a]apad[a]",
           "-map", "[v]", "-map", "[a]", "-t", f"{dur:.3f}", *ENCODE, scene / "scene.mp4")


def dialogue(scene, face, w, h, fps):
    pieces = json.loads((scene / "pieces.json").read_text())
    dur = duration(scene / "audio.wav")
    check_length(scene, face, "speaker0-only.wav")
    n = len(pieces)
    f = [f"color=c={CARD_BG}:s={w}x{h}:r={fps}:d={dur:.3f}[bg]",
         # The picture of the waveform is boosted so it reads on screen; the audio itself is untouched.
         f"[1:a]volume=14dB,showwaves=s={w}x{h // 4}:mode=cline:draw=full:scale=sqrt:rate={fps}:colors={WAVE},"
         f"format=yuva420p[wave]",
         "[bg][wave]overlay=0:(H-h)/2:shortest=1[o_]",
         f"[0:v]{fit(w, h, fps)},tpad=stop_mode=clone:stop_duration=3,split={n}" + "".join(f"[s{i}]" for i in range(n))]
    prev = "o_"
    for i, p in enumerate(pieces):
        length = p["end"] - p["start"]
        f.append(f"[s{i}]trim=start={p['at']:.3f}:end={p['at'] + length:.3f},"
                 f"setpts=PTS-STARTPTS+{p['start']:.3f}/TB[p{i}]")
        f.append(f"[{prev}][p{i}]overlay=eof_action=pass:enable='between(t,{p['start']:.3f},{p['end']:.3f})'[o{i}]")
        prev = f"o{i}"
    f.append("[1:a]apad[a]")
    ffmpeg("-i", face, "-i", scene / "audio.wav",
           "-filter_complex", ";".join(f), "-map", f"[{prev}]", "-map", "[a]", "-t", f"{dur:.3f}",
           *ENCODE, scene / "scene.mp4")


def chunk_clips(scene):
    """The rendered chunk videos of a chunked scene (only the ones that exist yet)."""
    if not (scene / "chunks.json").exists():
        return []
    return [scene / c["video"] for c in json.loads((scene / "chunks.json").read_text())["chunks"]
            if (scene / c["video"]).exists()]


def face_clip(scene):
    """A rendered face video in a scene, whichever way it was made. Chunk renders win over avatar.mp4."""
    clips = chunk_clips(scene)
    if clips:
        return clips[0]
    return scene / "avatar.mp4" if (scene / "avatar.mp4").exists() else None


def main():
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        sys.exit(__doc__)
    require_ffmpeg()
    project = Path(sys.argv[1])
    if not project.is_dir():
        sys.exit(f"No such folder: {project}")
    scenes = sorted(d for d in project.iterdir() if d.is_dir() and (d / "audio.wav").exists())
    if not scenes:
        sys.exit(f"No rendered scenes in {project}. Voice them first with fish_tts.py.")
    missing = [d.name for d in scenes if face_clip(d) is None]
    if missing:
        sys.exit(f"No face video yet in: {', '.join(missing)}. Save each render as <scene>/avatar.mp4 "
                 f"(or chunks/NN.mp4 for a chunked scene).")

    w, h, fps, rate = video_info(face_clip(scenes[0]))
    w, h = w - w % 2, h - h % 2
    captions, offset = [], 0.0
    for scene in scenes:
        face = join_chunks(scene, w, h, fps, rate) if chunk_clips(scene) else scene / "avatar.mp4"
        (dialogue if (scene / "pieces.json").exists() else single)(scene, face, w, h, fps)
        captions += caption_lines(json.loads((scene / "words.json").read_text()), offset, scene_text(scene))
        offset += duration(scene / "scene.mp4")
        print(f"{scene.name}: scene.mp4 done")

    concat = project / "concat.txt"
    concat.write_text("".join("file '" + str((s / "scene.mp4").resolve()).replace("'", "'\\''") + "'\n" for s in scenes))
    ffmpeg("-f", "concat", "-safe", "0", "-i", concat, "-c", "copy", "-movflags", "+faststart", project / "final.mp4")
    concat.unlink()
    (project / "final.srt").write_text(to_srt(captions))
    print(f"{project / 'final.mp4'} ({offset:.1f}s, {w}x{h} at {rate:.2f} fps) + final.srt")


if __name__ == "__main__":
    main()
