#!/usr/bin/env python3
"""Clone your voice from one or more clean clips, each with its transcript.

    python3 scripts/clone_voice.py "My AI Voice" me/voice/*.wav [--enhance]

Put a .txt with the exact words next to each clip (clip.wav + clip.txt). The
transcripts sharpen pronunciation. 1 to 2 minutes total across 3 to 5 clips of
you at the energy you want the clone to have works best. The voice is private,
so only your workspace can use it. Prints the new voice ID; put it in .env as
FISH_VOICE_ID.

(The Fish Audio MCP's create_voice_clone tool does the same from Claude Code,
minus the transcripts.)
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from fish_tts import load_env, need  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("title")
    p.add_argument("clips", nargs="+")
    p.add_argument("--enhance", action="store_true", help="Let Fish Audio denoise the clips (off by default: clean clips keep more of your tone)")
    args = p.parse_args()
    load_env()
    key = need("FISH_API_KEY")

    fields = [("type", "tts"), ("title", args.title), ("visibility", "private"), ("train_mode", "fast"),
              ("enhance_audio_quality", "true" if args.enhance else "false")]
    files = []
    for clip in args.clips:
        clip = Path(clip)
        files.append(("voices", clip.name, clip.read_bytes()))
        txt = clip.with_suffix(".txt")
        if txt.exists():
            fields.append(("texts", txt.read_text().strip()))
    n_texts = len([f for f in fields if f[0] == "texts"])
    if n_texts and n_texts != len(files):
        sys.exit("Give every clip a .txt transcript, or none of them.")

    boundary = uuid.uuid4().hex
    body = bytearray()
    for name, value in fields:
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
    for name, filename, data in files:
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                 f"Content-Type: application/octet-stream\r\n\r\n").encode() + data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        "https://api.fish.audio/model", data=bytes(body), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            model = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"Fish Audio returned {e.code}: {e.read().decode(errors='replace')[:500]}")
    print(json.dumps({"voice_id": model["_id"], "title": model.get("title"), "state": model.get("state")}))


if __name__ == "__main__":
    main()
