---
name: ai-clone-video
description: "Makes a talking-head video of the user without filming: writes the script, voices it in their cloned voice with Fish Audio's Drama 3 model, puts it on their face with Fish Audio's avatar generation, and assembles the finished clip with captions. Also fixes a flubbed line in a real take (new line plus lip sync), makes faceless narrated clips, and sets up the voice clone the first time. Triggers: make me a video, make a 30 second video, make a clip of me saying, AI clone video, avatar video, fix this line, I flubbed a line, redo a take, faceless video, faceless clip, cartoon skit, use my old footage, set up my voice, clone my voice."
---

# AI clone video

One prompt in, a finished video of the user out. Five steps: write, voice, quote, render, assemble. Voice costs pennies. Avatar renders cost plan credits, so nothing renders until the user approves the quote.

## Preflight (every run)

1. `.env` exists and has `FISH_API_KEY`. If not, copy `.env.example` to `.env` and ask the user to paste their key (fish.audio, API Keys). Never print the key.
2. The Fish Audio MCP is connected: call `get_credit_balance`. If the tools are missing, the user runs `claude mcp add --transport http fish-audio https://api.fish.audio/mcp`, then `/mcp` to sign in. Avatar video needs a Plus plan or higher.
3. `FISH_VOICE_ID` is set. If not, do Voice setup first.
4. The photo at `FISH_PHOTO` exists. If not, ask for one: front-facing, mouth closed, looking at the lens, good light. The avatar keeps the photo's shape, so 16:9 for YouTube and 9:16 for Shorts and Reels.

## Voice setup (first run only)

- Get 1 to 2 minutes of the user talking alone, at the energy they want the clone to have, with no music or other voices. Ask for files, or a link to one of their own videos (with yt-dlp installed: `yt-dlp -x --audio-format wav -o "me/source.%(ext)s" <url>`).
- Cut 3 to 5 clips of 15 to 30 seconds into `me/voice/` with `python3 scripts/cut_clip.py <source> me/voice/clip-1.wav --start <s> --end <s>`. Write each clip's exact words into a matching `.txt` (`clip-1.txt`).
- Clone it: `python3 scripts/clone_voice.py "My AI Voice" me/voice/*.wav`. That gives a private voice ID; write it to `FISH_VOICE_ID` in `.env`. (The MCP route works too: `get_upload_url`, then `create_voice_clone` with `visibility: private`. Set `confirm_voice_rights` only after the user confirms it's their own voice.)
- Only clone the user's own voice, or a voice they have permission to use.
- Test it: render one short tagged line, play it (`afplay` on Mac) and ask whether it sounds like them. If it sounds deeper or smoother than them, lower `FISH_TEMPERATURE` (0.3 is the default). If it sounds crunchy or clipped, keep `FISH_VOLUME_DB` at -6 or go lower.
- For dialogue, pick a second voice with `search_voices` and put its ID in `FISH_CLAUDE_VOICE_ID`.

## 1. Write the script

- Pick a kebab-case slug from the topic (`going-live-thursday`). Scene files go in `scenes/<slug>/01-<name>.txt`, `02-<name>.txt`, and so on.
- Length: about 2.7 spoken words per second, so 30 seconds is roughly 80 words. Keep every scene under 55 seconds (about 140 words), because one avatar job takes at most about a minute of audio. Split longer scripts at natural breaks.
- Make it sound like the user. If `me/style.md` or transcripts of their videos exist in `me/`, read them and borrow their openers, slang and rhythm. Use short sentences, one idea per line, and something unexpected every ten seconds or so. No corporate phrasing and no em dashes.
- Direct it with Drama 3. The file is sent exactly as written:
  - `[direction]` goes before the words it affects, written in plain English the way you'd brief a voice actor: `[excited, speaking fast]`, `[deadpan]`, `[voice drops to a whisper]`. It applies to everything after it until the next direction, so where you put it matters, including mid-sentence.
  - Sounds and pauses go where they happen: `[laughing]`, `[sigh]`, `[beat]`, `[pause]`.
  - Paired tags change only the words inside them: `<emphasis>…</emphasis>`, `<whisper>`, `<soft>`, `<fast>`, `<slow>`, `<stress>`, `<forceful>`.
  - `<spanish>…</spanish>` switches language for one phrase (experimental).
  - Dialogue: start each turn with `<|speaker:0|>` (the user) or `<|speaker:1|>` (the second voice). One generation voices the whole scene.
  - Spell out numbers when the reading matters ("eighty three").
- Show the user the script before rendering. Changing it is free right now.

## 2. Voice it (Fish Audio API, Drama 3, with timestamps)

```bash
python3 scripts/fish_tts.py scenes/<slug>/01-<name>.txt outputs/<slug>/01-<name>
```

- It prints the cost, the duration and `script_match`. If it prints `WORD MISMATCH`, re-render that scene once. If it happens again, show the user the mismatch.
- Dialogue scenes: also run `python3 scripts/split_speakers.py scenes/<slug>/02-<name>.txt outputs/<slug>/02-<name>`. Upload `speaker0-only.wav` for the avatar instead of `audio.wav`. The other voice's lines never go on the user's face.
- Play each scene for the user (`afplay outputs/<slug>/01-<name>/audio.wav`) and get a thumbs-up before quoting avatar credits.

## 3. Quote the avatar (Fish Audio MCP)

- Get `workspace_id` from `get_credit_balance`.
- Pick the model: `list_media_models` with capability `avatar_audio`. Take the lowest `credits_per_input_second` model whose `get_media_model` says it accepts `sourceAudio` at least as long as your longest scene. Default to 720P; 1080P costs about double.
- Photo: if `FISH_PHOTO_KEY` is in `.env`, reuse it. Otherwise call `create_media_upload` (exact byte size and content type), run `bash scripts/upload.sh me/photo.jpg "<upload_url>" image/jpeg` (it must print 200), and save the `object_key` to `FISH_PHOTO_KEY` in `.env`.
- Audio: upload each scene's `audio.wav` (or `speaker0-only.wav`) the same way with content type `audio/wav`.
- Call `estimate_video_generation` for each scene with `ref` = photo, `sourceAudio` = that scene's audio, and the same parameters you'll render with.
- Show the user one table: scene, seconds, credits, total, and the balance left afterwards. **Stop and wait for an explicit yes.** Nothing is charged before that.

## 4. Render the avatar

- Call `generate_video` with exactly the estimated inputs and parameters, plus its `expected_credits`, its `pricing_version`, and `idempotency_key` = `<slug>-<scene>-<audio file size in bytes>`, so a retry can never charge twice. Submit all scenes in one turn.
- Never resubmit on your own. If the price changed or a job failed (failed jobs are refunded), tell the user.
- Check all running jobs together with `get_generation_status`, waiting `poll_after_seconds` (about 60) between checks. Each video takes a few minutes.
- Download each finished result: `curl -sSL -o outputs/<slug>/<scene>/avatar.mp4 "<media.url>"`. If the download fails, give the user the `view_url`.

## 5. Assemble

```bash
python3 scripts/assemble.py outputs/<slug>
```

This writes `outputs/<slug>/final.mp4` and `final.srt`. Open the video (`open` on Mac) and tell the user how long it is, what it cost (API dollars plus plan credits), and anything that looked off.

## Other jobs

### Fix a flubbed line in a real take

The rest of the take stays real. Only the flubbed line is replaced: the user's avatar says the corrected line in their cloned voice, shot from a still of the same take so it matches.

1. Find the line. Use the times the user gives you. If they don't give any, transcribe the take with the MCP's `speech_to_text` (upload with `get_upload_url`; `flash` is the cheaper model) and find the words.
2. `python3 scripts/fix_take.py prepare <take> --start <s> --end <s> --text "<corrected line, tags allowed>" --out outputs/fix-<slug>`. Set `--end` at the end of the pause after the flub, because everything between start and end gets replaced. Pass `--frame-at <s>` for a moment in that shot where their mouth is closed and they're looking at the lens. Play `line.wav` for the user.
3. Quote it. The default is the avatar route: upload `frame.jpg` (`image/jpeg`) and `line.wav` (`audio/wav`), then call `estimate_video_generation` with `ref` and `sourceAudio` on the cheapest `avatar_audio` model that matches the take's resolution. The other route is lip sync on the real footage, which keeps their real head motion: upload `clip.mp4` and use a `video_audio` model with `sourceVideo` and `sourceAudio`. Show the credits and wait for a yes.
4. Render with `generate_video`, download the result to `outputs/fix-<slug>/synced.mp4`, then run `python3 scripts/fix_take.py splice <take> outputs/fix-<slug>`. Open `compare.mp4` (the original line, then the fix) and `fixed.mp4` (the whole take).

### Use old footage instead of a photo

A lip sync on real footage of the user looks more real than a photo avatar: it keeps their real light and head motion and only redoes the mouth.

1. Voice the scene as usual. Find stretches in one of the user's old videos where they look straight into the lens (check the eyes on stills; skip anything they've asked to keep out).
2. `python3 scripts/source_from_take.py <old video> outputs/<slug>/<scene> --ranges 53.3-57.5,92.0-97.8,... --out outputs/<slug>/<scene>/source.mp4`. It jump-cuts those stretches on the pauses in the new audio, at exactly the audio's length.
3. Upload `source.mp4` (`video/mp4`) and `audio.wav`, quote a `video_audio` model (`list_media_models` with capability `video_audio`) with `sourceVideo` and `sourceAudio`, wait for a yes, render, and save the result as `avatar.mp4`. `assemble.py` puts the clean audio back under it.

### Cartoon skit

A dialogue scene acted out by cartoon characters, one shot per line.

1. Write it as a dialogue scene, then voice it and run `split_speakers.py` as usual. Then `python3 scripts/skit.py split outputs/<slug>/<scene>` writes one clip per line into `shots/`.
2. Make a character sheet per character with an image `edit` model (the user's photo as the reference for their cartoon), then the first wide shot from both sheets. Generate every other keyframe with both sheets plus that first shot as references, so the characters and room stay the same. The speaking character's face must be clear; turn the other one away, blur them, or hide their face. Ask for blank props: image models add real brand logos unless told not to. Quote all the images first.
3. For each shot, quote a talking avatar (`avatar_audio`) with the keyframe as `ref` and `shotNN.wav` as `sourceAudio`. Use a model that takes a prompt and say who talks and who stays still, or the model can animate both faces. Wait for a yes, render, and save each one as `shots/shotNN.mp4`.
4. `python3 scripts/skit.py assemble outputs/<slug>/<scene>` cuts the shots together over the original audio and writes `skit.mp4`.

### Faceless clip

1. Write the narration with the same rules as step 1 above and voice it with `fish_tts.py` into `outputs/<slug>/narration`.
2. Get footage: the user's own b-roll, stock they have the rights to, or clips from Fish Audio's video models (`list_media_models` with capability `t2v`, then quote and wait for a yes as usual). No game, movie or TV footage they don't own.
3. `python3 scripts/faceless.py outputs/<slug>/narration <footage files...> --out outputs/<slug>/final.mp4` (add `--vertical` for Shorts and Reels). It writes `final.mp4` and `final.srt`.

## Rules

- `.env`, `me/` and `outputs/` stay local; they're gitignored. Never print the API key. Treat voice IDs like passwords: anyone holding an unlisted voice ID can use that voice, which is why clones are created private.
- Every Fish Audio step runs from here, through the scripts or the MCP. Don't send the user to the web app.
- Quote before every paid generation and wait for a yes. A yes covers the quote it answered, nothing else.
