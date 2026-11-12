"""Shared helpers for the scripts in this folder. Standard library only."""
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.fish.audio"
KEYS_URL = "https://fish.audio/app/api-keys"
BILLING_URL = "https://fish.audio/app/developers/billing/"


def load_env():
    """Read .env into os.environ (real environment variables win)."""
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def need(name):
    value = os.environ.get(name, "")
    if not value:
        hint = {
            "FISH_API_KEY": f"Create a key at {KEYS_URL} and paste it into .env.",
            "FISH_VOICE_ID": "Clone your voice first (python3 scripts/voice_samples.py, then scripts/clone_voice.py).",
            "FISH_CLAUDE_VOICE_ID": "Pick a second voice with the Fish Audio MCP's search_voices and save its ID to .env.",
        }.get(name, "Fill it in .env (see .env.example).")
        sys.exit(f"{name} is empty. {hint}")
    return value


def set_env(name, value):
    """Write NAME=value into .env, replacing the existing line or adding one."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        shutil.copy(ROOT / ".env.example", env_file)
    lines = env_file.read_text().splitlines()
    for i, line in enumerate(lines):
        if re.match(rf"\s*{re.escape(name)}\s*=", line):
            lines[i] = f"{name}={value}"
            break
    else:
        lines += ["", f"{name}={value}"]
    env_file.write_text("\n".join(lines) + "\n")
    os.environ[name] = str(value)


def mask(secret):
    """Enough of an ID to recognize it, never enough to use it."""
    return f"{secret[:4]}...{secret[-4:]}" if len(secret) > 10 else "(set)"


def require_ffmpeg():
    missing = [t for t in ("ffmpeg", "ffprobe") if not shutil.which(t)]
    if missing:
        sys.exit(f"{' and '.join(missing)} not found. Install ffmpeg: {ffmpeg_install_hint()}")


def ffmpeg_install_hint():
    if sys.platform == "darwin":
        return "brew install ffmpeg"
    if sys.platform.startswith("win"):
        return "winget install Gyan.FFmpeg  (then reopen the terminal)"
    return "sudo apt install ffmpeg  (or your distro's package manager)"


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *[str(a) for a in args]], check=True)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def video_info(path):
    """(width, height, fps as 'num/den', fps as float) of the first video stream."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip().split("\n")[0].split(",")
    num, den = (out[2].split("/") + ["1"])[:2]
    return int(out[0]), int(out[1]), f"{num}/{den}", int(num) / int(den)


def loudness(src_args):
    """(integrated LUFS, true peak dBFS) for ffmpeg input args such as ['-i', 'a.wav']."""
    stats = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", *[str(a) for a in src_args],
                            "-af", "ebur128=peak=true", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
    lufs = re.findall(r"I:\s+(-?[\d.]+) LUFS", stats)
    peak = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", stats)
    if not lufs or not peak:
        sys.exit("Could not measure loudness. Is the file empty or silent?")
    return float(lufs[-1]), float(peak[-1])


def level_gain(src_args, target_lufs, ceiling_db=-1.0):
    """Plain gain (dB) that brings the audio to target_lufs without the peak passing ceiling_db.

    Never loudnorm's one-pass mode: that compresses, and compression is what makes TTS sound crunchy.
    """
    lufs, peak = loudness(src_args)
    if lufs < -65:  # silence
        return 0.0
    return min(target_lufs - lufs, ceiling_db - peak)


def spoken_words(text):
    """The words a script should produce, with every tag stripped."""
    text = re.sub(r"<\|[^|]*\|>|<[^>]*>|\[[^\]]*\]", " ", text)
    return [w for w in (re.sub(r"[^\w']", "", t.lower()) for t in text.split()) if w]


def fish_request(path, key, data=None, headers=None, method=None, timeout=300):
    """Call the Fish Audio API and return the open response. Exits with a plain-English message on failure."""
    req = urllib.request.Request(API + path, data=data, method=method or ("POST" if data is not None else "GET"),
                                 headers={"Authorization": f"Bearer {key}", **(headers or {})})
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        sys.exit(explain_http_error(e))
    except urllib.error.URLError as e:
        sys.exit(f"Could not reach Fish Audio ({e.reason}). Check your connection and try again.")


def explain_http_error(e):
    body = e.read().decode(errors="replace")[:400]
    reason = {
        401: f"Fish Audio rejected the API key. Check FISH_API_KEY in .env (keys: {KEYS_URL}).",
        402: f"Out of API credit. The voice runs on prepaid API credit, separate from your plan's credits. "
             f"Add a few dollars at {BILLING_URL}",
        404: "Fish Audio could not find that voice. Check the voice ID in .env.",
        413: "That file is too large for Fish Audio.",
        429: "Fish Audio is rate limiting you. Wait a few seconds and run it again, one request at a time.",
    }.get(e.code, "")
    if "Reference not found" in body:
        reason = ("Fish Audio does not know that voice ID on this account. Check FISH_VOICE_ID (and "
                  "FISH_CLAUDE_VOICE_ID) in .env; a voice cloned on another Fish Audio account won't be found here.")
    return f"Fish Audio returned {e.code}. {reason}\n{body}".strip()


def api_json(path, key, timeout=30):
    """GET a JSON document. Returns (data, None) or (None, error message); never exits."""
    req = urllib.request.Request(API + path, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read()), None
    except urllib.error.HTTPError as e:
        return None, f"{e.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return None, f"network: {getattr(e, 'reason', e)}"


def multipart(fields, files):
    """Encode form fields [(name, value)] and files [(name, filename, bytes)]. Returns (body, content type)."""
    import uuid
    boundary = uuid.uuid4().hex
    body = bytearray()
    for name, value in fields:
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
    for name, filename, data in files:
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                 f"Content-Type: application/octet-stream\r\n\r\n").encode() + data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"
