#!/usr/bin/env python3
"""Clone your voice from one or more clean clips, each with its transcript.

    python3 scripts/clone_voice.py "My AI Voice" me/voice/*.wav [--enhance]

Put a .txt with the exact words next to each clip (clip.wav + clip.txt);
voice_samples.py makes both for you. The transcripts sharpen pronunciation.
1 to 2 minutes total across 3 to 5 clips of you at the energy you want the
clone to have works best.

The voice is created private, so only your account can use it. The new voice ID
goes straight into .env as FISH_VOICE_ID (never printed in full: anyone holding
a voice ID that isn't private can speak with that voice), along with your
normal pitch as FISH_VOICE_PITCH_HZ, which the take picker uses to tell when a
render drifts away from sounding like you.

Only clone your own voice, or a voice you have permission to use.

(The Fish Audio MCP's create_voice_clone tool also clones from Claude Code, but
it cannot send transcripts and makes voices unlisted unless told otherwise.)
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import duration, fish_request, load_env, mask, multipart, need, require_ffmpeg, set_env  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("title")
    p.add_argument("clips", nargs="+")
    p.add_argument("--enhance", action="store_true", help="Let Fish Audio denoise the clips (off by default: clean clips keep more of your tone)")
    p.add_argument("--env-name", default="FISH_VOICE_ID", help="which .env value to save the new voice ID to")
    p.add_argument("--no-save", action="store_true", help="print the voice ID instead of saving it to .env")
    args = p.parse_args()
    require_ffmpeg()
    load_env()
    key = need("FISH_API_KEY")

    fields = [("type", "tts"), ("title", args.title), ("visibility", "private"), ("train_mode", "fast"),
              ("enhance_audio_quality", "true" if args.enhance else "false")]
    files, total = [], 0.0
    for clip in args.clips:
        clip = Path(clip)
        if not clip.is_file():
            sys.exit(f"No such file: {clip}")
        files.append(("voices", clip.name, clip.read_bytes()))
        total += duration(clip)
        txt = clip.with_suffix(".txt")
        if txt.exists() and txt.read_text().strip():
            fields.append(("texts", txt.read_text().strip()))
    n_texts = len([f for f in fields if f[0] == "texts"])
    if n_texts and n_texts != len(files):
        sys.exit("Give every clip a .txt transcript, or none of them.")
    if total < 10:
        sys.exit(f"Only {total:.0f}s of audio. Fish Audio needs at least 10 seconds, and 1 to 2 minutes sounds far closer.")
    if total < 45:
        print(f"Note: {total:.0f}s of audio will work, but 1 to 2 minutes sounds noticeably more like you.", file=sys.stderr)

    body, content_type = multipart(fields, files)
    with fish_request("/model", key, data=body, headers={"Content-Type": content_type}) as resp:
        model = json.loads(resp.read())
    voice_id = model["_id"]

    summary = {"title": model.get("title"), "state": model.get("state"), "visibility": model.get("visibility"),
               "clips": len(files), "seconds": round(total), "transcripts": bool(n_texts)}
    if args.no_save:
        summary["voice_id"] = voice_id
    else:
        set_env(args.env_name, voice_id)
        summary["saved_to"] = f".env as {args.env_name} ({mask(voice_id)})"
        try:
            from voice_check import median_pitch
            pitches = [hz for hz in (median_pitch(c) for c in args.clips) if hz]
            if pitches:
                hz = round(statistics.median(pitches))
                set_env(args.env_name.replace("_ID", "_PITCH_HZ"), hz)
                summary["normal_pitch_hz"] = hz
        except Exception as e:  # the clone exists either way
            print(f"(could not measure pitch: {e})", file=sys.stderr)
    print(json.dumps(summary))
    if model.get("visibility") not in (None, "private"):
        print("WARNING: this voice is not private. Anyone with its ID can use it.", file=sys.stderr)


if __name__ == "__main__":
    main()
