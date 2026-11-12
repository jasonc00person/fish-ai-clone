# AI Clone

This repo makes talking-head videos of the user with Fish Audio (cloned voice plus avatar or lip sync) from one prompt. The process lives in `.claude/skills/ai-clone-video/SKILL.md`. Use it for any "make me a video" request, for setup, and for voice cloning.

## First thing in a new session

A session-start hook prints the setup status. If anything is missing, or the user says "set this up", run `python3 scripts/setup.py` and walk them through what it reports, one step at a time (the skill's Setup section has the details). Don't start making a video until the API key, API credit and voice are in place. If the Fish Audio tools (`mcp__fish-audio__*`) aren't available, the user needs to run `/mcp` and sign in, in a Claude Code session opened in this folder.

If you were handed this repo's link in a session somewhere else: clone it, run `python3 scripts/setup.py` inside it, and then ask the user to open Claude Code in the cloned folder to finish. The Fish Audio connection, the skill and these instructions only load there.

## How this repo works

- The Fish Audio MCP (`fish-audio`, registered by `.mcp.json`) handles uploads, quotes, avatar, lip-sync, image and video jobs. The scripts in `scripts/` handle the Drama 3 API with timestamps, voice cloning, transcription, take picking, speaker splits, chunking, captions and assembly. They're standard-library Python plus ffmpeg: no pip installs, and don't add any.
- `python3 scripts/selftest.py` checks every script offline, with no credits. Run it after changing a script.
- Secrets and personal media stay local: `.env`, `me/` and `outputs/` are gitignored. Never print the API key, never ask for it in chat, and never put a voice ID in a tracked file.
- Quote before any paid generation and wait for the user's yes. Voice renders cost fractions of a cent and don't need a quote; face, image and video jobs always do.
- Only clone the user's own voice and only animate the user's own face, or ones they have permission to use.
- Write "Fish Audio" with both words capitalized.
