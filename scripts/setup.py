#!/usr/bin/env python3
"""Set this project up and report what is still missing. Safe to run as often as you like.

    python3 scripts/setup.py             # do everything it can, check the rest, say what's next
    python3 scripts/setup.py --open-env  # open .env in a text editor to paste the API key
    python3 scripts/setup.py --hook      # one-screen offline status (Claude Code runs this at session start)

What it does by itself: makes .env from .env.example, makes the me/, scenes/ and
outputs/ folders, registers the Fish Audio MCP with Claude Code, and checks the
API key, API credit, cloned voice and photo against Fish Audio.

What only you can do: install ffmpeg (it prints the command), sign in to Fish
Audio (claude mcp login fish-audio), and paste an API key into .env.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BILLING_URL, KEYS_URL, ROOT, api_json, ffmpeg_install_hint, load_env  # noqa: E402

MCP_NAME, MCP_URL = "fish-audio", "https://api.fish.audio/mcp"
MCP_ADD = f"claude mcp add --transport http {MCP_NAME} {MCP_URL}"
OK, TODO, WARN, OPTIONAL = "ok", "todo", "warn", "opt"


def env_values():
    values = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def ensure_files():
    """Create .env and the working folders. Returns notes about what was created."""
    made = []
    env_file, example = ROOT / ".env", ROOT / ".env.example"
    if not env_file.exists():
        shutil.copy(example, env_file)
        made.append("created .env")
    else:
        # Add any setting a newer .env.example has that this .env doesn't.
        have = env_values()
        missing = [line for line in example.read_text().splitlines()
                   if "=" in line and not line.startswith("#") and line.split("=", 1)[0].strip() not in have]
        if missing:
            with env_file.open("a") as f:
                f.write("\n" + "\n".join(missing) + "\n")
            made.append(f"added {len(missing)} new setting(s) to .env")
    for folder in ("me/voice", "scenes", "outputs"):
        if not (ROOT / folder).is_dir():
            (ROOT / folder).mkdir(parents=True)
            made.append(f"created {folder}/")
    return made


def check_ffmpeg():
    missing = [t for t in ("ffmpeg", "ffprobe") if not shutil.which(t)]
    if missing:
        return TODO, f"ffmpeg is not installed. Run: {ffmpeg_install_hint()}"
    version = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.split("\n")[0]
    return OK, " ".join(version.split()[:3])


def check_key(env, online):
    key = env.get("FISH_API_KEY", "")
    if not key:
        return TODO, (f"No Fish Audio API key yet. Create one at {KEYS_URL} and paste it into .env after "
                      f"FISH_API_KEY= (python3 scripts/setup.py --open-env opens the file). Don't paste it in chat.")
    if not online:
        return OK, "API key is in .env"
    data, err = api_json("/wallet/self/api-credit", key)
    if err == "401":
        return TODO, f"Fish Audio rejected the API key in .env. Make a new one at {KEYS_URL} and replace it."
    if err:
        return WARN, f"API key is in .env, but Fish Audio could not be reached to check it ({err})."
    credit = float(data.get("credit") or 0)
    if credit <= 0:
        return TODO, (f"API key works, but the API credit balance is $0. The voice runs on prepaid API credit "
                      f"(separate from your plan). Add a few dollars at {BILLING_URL}: a 30 second script costs "
                      f"well under a cent.")
    return OK, f"API key works, ${credit:.2f} of API credit"


def check_mcp(online):
    if not online:
        return None
    claude = shutil.which("claude")
    if not claude:
        return WARN, ("Could not find the claude command to check the Fish Audio MCP from here. This folder's "
                      ".mcp.json registers it; if the Fish Audio tools ask you to sign in, type /mcp in the terminal "
                      "version of Claude Code, or add https://api.fish.audio/mcp as a custom connector in Claude's settings.")

    def status():
        try:
            r = subprocess.run([claude, "mcp", "get", MCP_NAME], cwd=ROOT, capture_output=True, text=True, timeout=60)
            return r.stdout + r.stderr
        except (subprocess.TimeoutExpired, OSError):
            return ""

    out = status()
    registered_here = "Scope: Local" in out or "Scope: User" in out
    if "Connected" not in out and not registered_here:
        # Registering it for this folder skips the "approve this project's MCP server?" question.
        try:
            subprocess.run([claude, "mcp", "add", "--transport", "http", MCP_NAME, MCP_URL], cwd=ROOT,
                           capture_output=True, text=True, timeout=60)
        except (subprocess.TimeoutExpired, OSError):
            pass
        out = status()
    if "Connected" in out:
        return OK, "Fish Audio MCP is connected"
    if "Needs authentication" in out or "Scope:" in out:
        return TODO, ("Fish Audio MCP is registered but not signed in. The user runs this in a terminal, from this "
                      "folder: claude mcp login fish-audio  (the browser opens; sign in and pick the team). In the "
                      "terminal version of Claude Code, /mcp then fish-audio also works; the desktop app's /mcp "
                      "does not list it.")
    return TODO, f"Fish Audio MCP is not registered. Run: {MCP_ADD}  then: claude mcp login {MCP_NAME}"


def check_voice(env, online):
    voice = env.get("FISH_VOICE_ID", "")
    if not voice:
        return TODO, ("No cloned voice yet. Tell Claude: \"set up my voice from <a video of you talking, or a link "
                      "to one>\". It needs 1 to 2 minutes of you talking alone.")
    key = env.get("FISH_API_KEY", "")
    if not (online and key):
        return OK, "voice ID is in .env"
    data, err = api_json(f"/model/{voice}", key)
    if err == "404":
        return TODO, "The voice ID in .env does not exist on this Fish Audio account. Clone your voice again."
    if err:
        return WARN, f"voice ID is in .env (could not check it: {err})"
    if data.get("visibility") not in (None, "private"):
        return WARN, (f"Voice \"{data.get('title')}\" is {data.get('visibility')}, not private: anyone with its ID "
                      f"can use it. Re-clone it with scripts/clone_voice.py to get a private one.")
    return OK, f"voice \"{data.get('title')}\" is ready ({data.get('state')}, private)"


def check_photo(env):
    photo = ROOT / (env.get("FISH_PHOTO") or "me/photo.jpg")
    try:
        shown = photo.relative_to(ROOT)
    except ValueError:  # a photo kept outside this folder
        shown = photo
    if photo.is_file():
        shape = ""
        if shutil.which("ffprobe"):
            r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                "stream=width,height", "-of", "csv=p=0", str(photo)], capture_output=True, text=True)
            try:
                w, h = (int(x) for x in r.stdout.strip().split(",")[:2])
                shape = f" ({w}x{h}, {'vertical' if h > w else 'horizontal'}: the avatar video comes out the same shape)"
            except ValueError:
                pass
        return OK, f"photo at {shown}{shape}"
    return OPTIONAL, (f"No photo at {shown}. For a photo avatar, add one clear front-facing photo: "
                  f"mouth closed, looking into the lens, 16:9 for YouTube or 9:16 for Shorts and Reels. "
                  f"(Not needed for faceless clips or for lip sync on your own footage.)")


def run_checks(online):
    env = env_values()
    checks = [("ffmpeg", check_ffmpeg()), ("API key", check_key(env, online))]
    mcp = check_mcp(online)
    if mcp:
        checks.append(("Fish Audio MCP", mcp))
    checks += [("Voice", check_voice(env, online)), ("Photo", check_photo(env))]
    return checks


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--hook", action="store_true", help="offline status only, for the session-start hook")
    p.add_argument("--open-env", action="store_true", help="open .env in a text editor")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()

    if sys.version_info < (3, 8):
        sys.exit(f"Python 3.8 or newer is needed; this is {sys.version.split()[0]}.")
    if not (ROOT / ".env.example").exists():
        sys.exit(f"{ROOT} doesn't look like the AI Clone repo (.env.example is missing).")

    if a.hook:
        ready = (ROOT / ".env").exists()
        checks = run_checks(online=False) if ready else []
        todo = [msg for _, (state, msg) in checks if state == TODO]
        if not ready:
            print("AI Clone: first run. Before anything else, run `python3 scripts/setup.py` and walk the user "
                  "through what it reports (see \"Setup\" in the ai-clone-video skill).")
        elif todo:
            print("AI Clone setup is not finished. Run `python3 scripts/setup.py` for the full check. Still to do:")
            for msg in todo:
                print(f"- {msg}")
        else:
            photo = "" if all(state != OPTIONAL for _, (state, _) in checks) else " (no photo yet: fine unless they want a photo avatar)"
            print(f"AI Clone: API key and voice are in place{photo}. If a Fish Audio tool call fails, run "
                  "`python3 scripts/setup.py` to see why.")
        return

    made = ensure_files()
    if a.open_env:
        env_file = str(ROOT / ".env")
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", "-t", env_file], check=True)
            elif sys.platform.startswith("win"):
                os.startfile(env_file)  # noqa: S606
            else:
                subprocess.run(["xdg-open", env_file], check=True)
            print(f"Opened {env_file}. Paste the key after FISH_API_KEY= and save. Keys: {KEYS_URL}")
        except (OSError, subprocess.CalledProcessError):
            print(f"Open {env_file} in any text editor, paste the key after FISH_API_KEY= and save. Keys: {KEYS_URL}")
        return

    load_env()
    checks = run_checks(online=True)
    if a.json:
        print(json.dumps({"created": made, "checks": [{"name": n, "state": s, "message": m} for n, (s, m) in checks]},
                         indent=1))
        return
    print("AI Clone setup")
    for note in made:
        print(f"  [done] {note}")
    for name, (state, msg) in checks:
        print(f"  [{state:4}] {name}: {msg}")
    todo = [(n, m) for n, (s, m) in checks if s == TODO]
    if todo:
        print(f"\nNext: {todo[0][1]}")
        print("Run this again after each step.")
    elif any(s == OPTIONAL for _, (s, _) in checks):
        print("\nReady for faceless clips, voiceovers and lip sync on your own footage. Add a photo for a photo "
              "avatar. Try: \"make me a 20 second faceless clip about <topic>\"")
    else:
        print("\nEverything is in place. Try: \"make me a 30 second video about <topic>\"")


if __name__ == "__main__":
    main()
