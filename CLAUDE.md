# AI Clone

This repo makes talking-head videos of the user with Fish Audio (cloned voice plus avatar) from one prompt. The process lives in `.claude/skills/ai-clone-video/SKILL.md`. Use it for any "make me a video" request and for first-time voice setup.

- The Fish Audio MCP (`fish-audio`) handles voice cloning, uploads and avatar jobs. The scripts in `scripts/` handle the Drama 3 API with timestamps, speaker splits, captions and assembly. They're standard-library Python plus ffmpeg.
- Secrets and personal media stay local: `.env`, `me/` and `outputs/` are gitignored. Never print the API key or put a voice ID in a tracked file.
- Quote before any paid generation and wait for the user's yes.
