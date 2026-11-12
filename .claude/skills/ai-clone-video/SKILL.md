---
name: ai-clone-video
description: "Makes a talking-head video of the user without filming: writes the script, voices it in their cloned voice with Fish Audio's Drama 3 model, puts it on their face with Fish Audio's avatar or lip-sync generation, and assembles the finished clip with captions. Also sets the project up the first time (Fish Audio connection, API key, voice clone), fixes a flubbed line in a real take, makes faceless narrated clips, cartoon skits and two-voice dialogue, and renders the same script in other languages. Triggers: set this up, set up the Fish Audio MCP, make me a video, make a 30 second video, make a clip of me saying, AI clone video, avatar video, fix this line, I flubbed a line, redo a take, faceless video, faceless clip, voiceover, cartoon skit, dialogue, use my old footage, lip sync, set up my voice, clone my voice, in Spanish."
---

# AI clone video

One prompt in, a finished video of the user out. Five steps: write, voice, quote, render, assemble. Voice costs fractions of a cent, so iterate there freely. Face renders cost plan credits, so nothing renders until the user approves a quote.

Deeper notes, read them when you reach that step:
- `reference/voice.md`: cloning, directing Drama 3, picking takes, two-voice scenes, other languages
- `reference/face.md`: photo avatar vs lip sync on real footage, the models, limits, prices, the upload and quote contract
- `reference/skit.md`: cartoon skits with consistent characters, both ways to make them
- `reference/troubleshooting.md`: symptom, cause, fix

## Setup (first run, or whenever something is missing)

Run `python3 scripts/setup.py`. It creates `.env` and the folders, registers the Fish Audio MCP, checks the key, the API credit, the voice and the photo, and prints what is still missing with the exact next step. Do what it says, one item at a time, and run it again after each one. The pieces only the user can do:

1. **ffmpeg**: if missing, run the install command it prints (ask first; it installs software).
2. **Sign in to Fish Audio (MCP)**: the user runs `/mcp`, picks `fish-audio` and signs in in the browser. If the tools still aren't there, they start a new Claude Code session in this folder (project settings and MCP servers only load when Claude Code is opened here). `claude mcp login fish-audio` in a terminal does the same sign-in.
3. **API key**: `python3 scripts/setup.py --open-env` opens `.env`; the user creates a key at https://fish.audio/app/api-keys and pastes it after `FISH_API_KEY=`. Never ask them to paste it in chat, and never print it.
4. **API credit**: the voice bills prepaid API credit, a separate wallet from the plan's credits. A few dollars at https://fish.audio/app/developers/billing/ covers hundreds of videos. Without it every render fails with a 402.
5. **A plan with video** (Plus or higher) only if they want a face. Faceless clips and voiceovers need no plan.

Then check both wallets belong to the same account: `get_credit_balance` (MCP) shows the plan and its credits; `setup.py` shows the API credit. The MCP sign-in and the API key can point at different Fish Audio accounts without any error, and then the voice ID from one won't exist on the other.

If the user got here by pasting the repo link into a session somewhere else: clone it, run `python3 scripts/setup.py` inside it, then tell them to open Claude Code in that folder to finish (sign-in and the skill need it).

`python3 scripts/selftest.py` proves every script works on this machine without spending anything. Run it if anything local looks broken.

## Voice setup (once)

Full notes in `reference/voice.md`. The short version:

1. Get footage of the user talking alone: files on their computer (old videos, raw takes), or a link to one of their own videos (`yt-dlp -x --audio-format wav -o "me/source.%(ext)s" <url>` if yt-dlp is installed).
2. `python3 scripts/voice_samples.py <files...>` finds 15 to 30 second stretches of steady speech, cuts 3 to 5 clips into `me/voice/`, transcribes each one and skips anything with a second speaker or music. Aim for 1 to 2 minutes total, at the energy the clone should have.
3. Read the `.txt` transcripts and fix misheard names (brand names especially). Ask the user to confirm it is their own voice.
4. `python3 scripts/clone_voice.py "My AI Voice" me/voice/*.wav` creates a private clone and saves the voice ID and their normal pitch to `.env`.
5. Test it: `python3 scripts/fish_tts.py examples/test-tags.txt outputs/voice-test --takes 2`, play it (`afplay outputs/voice-test/audio.wav` on a Mac) next to one of their real clips at the same loudness, and ask if it sounds like them. Fixes for "deeper", "crunchy" and "not like me" are in the troubleshooting file.
6. For dialogue, pick a second voice with `search_voices`, audition it by ear (see `reference/voice.md`), and save it as `FISH_CLAUDE_VOICE_ID`.

## 1. Write the script

- Pick a kebab-case slug from the topic (`going-live-thursday`). Scene files go in `scenes/<slug>/01-<name>.txt`, `02-<name>.txt`, and so on.
- Length: about 2.7 spoken words per second, so 30 seconds is roughly 80 words. A scene can be any length: `chunk_scene.py` splits long ones at sentence breaks later. Split into separate scene files only where the video changes subject or look.
- Make it sound like the user. If `me/style.md` or transcripts of their videos exist in `me/`, read them and borrow their openers, slang and rhythm. Short sentences, one idea per line, something unexpected every ten seconds or so. No corporate phrasing, no lists of three, no em dashes. If the script includes a joke with a number or a fact in it, check the fact.
- Direct it with Drama 3. The file is sent exactly as written:
  - `[direction]` goes before the words it affects, in plain English, the way you'd brief a voice actor: `[excited, speaking fast]`, `[deadpan]`, `[voice drops to a whisper]`. It applies to everything after it until the next direction, so position matters, including mid-sentence.
  - Keep directions short (one to three words) and close to the energy of the clips the voice was cloned from. Strong acting directions (`[panicking]`, `[laughing]`) change who it sounds like. More expression comes from more short tags, not longer ones.
  - Sounds and pauses go where they happen: `[laughing]`, `[sigh]`, `[beat]`, `[pause]`, `[long pause]`.
  - Paired tags change only the words inside them: `<emphasis>…</emphasis>` (stretches the word), `<whisper>`, `<soft>`, `<fast>`, `<slow>`, `<stress>`, `<forceful>`.
  - `<spanish>…</spanish>` (also french, german, japanese, chinese, korean, italian) switches language for one phrase. Experimental.
  - Dialogue: start each turn with `<|speaker:0|>` (the user) or `<|speaker:1|>` (the second voice). One generation voices the whole scene.
  - Spell out numbers when the reading matters ("eighty three"). A comma instead of a full stop between two short sentences avoids a choppy read.
- Show the user the script before rendering. Changing it is free right now. Lock the words before any face render: every credit spent on a face is for one exact audio file.

Worked examples with notes: `examples/video/` (the scenes from the video), `examples/faceless/`, `examples/cartoon-skit/`.

## 2. Voice it (Fish Audio API, Drama 3, with timestamps)

```bash
python3 scripts/fish_tts.py scenes/<slug>/01-<name>.txt outputs/<slug>/01-<name> --takes 3
```

- `--takes 3` renders three takes, measures each (pitch against the user's normal pitch, how far any whisper drops) and keeps the best. Takes vary a lot: the same whisper line dropped 5, 7 and 14 dB across three takes. All takes stay in `takes/`; `--pick N` swaps one in.
- It prints cost, duration and `script_match`. `WORD MISMATCH` means the audio's words differ from the script: render again, and if it repeats, show the user.
- Dialogue scenes: `--temperature 0.15 --takes 6` (voices bleed into each other at higher temperatures), then `python3 scripts/split_speakers.py outputs/<slug>/02-<name>`. It writes `speaker0-only.wav`, the only audio that goes on the user's face.
- `python3 scripts/voice_check.py outputs/<slug>/<scene>` shows pitch per turn and whisper depth for any render.
- Other language: write the scene in that language and add `--language es` (or `es-MX`, `fr`, and so on). Same voice ID, same tags.
- Play every scene for the user and get a thumbs-up before quoting any face render. If they compare it to their real voice, play both at the same loudness.

## 3. Choose the face and quote it (Fish Audio MCP)

Three ways to put the voice on a face. Details, limits and prices in `reference/face.md`.

| Route | What it needs | Looks like | Use when |
|---|---|---|---|
| Photo avatar | one photo | their face animated from a still: head moves, no hands | quickest, no footage needed |
| Lip sync on real footage | a take of them looking into the lens, at least as long as the audio | their real video with the mouth redone | most realistic; this is what the video used |
| No face | b-roll or stills | narration over footage | faceless channels, voiceovers |

Default to the photo avatar unless they have (or will record) a lens-facing take. Then:

- `get_credit_balance` for `workspace_id` and the balance.
- Pick the model with `list_media_models` (`capability: avatar_audio` for a photo, `video_audio` for lip sync) and read `get_media_model` once: it lists the parameters, the input roles and the limits. Prices and limits change, so trust the live answer over anything written here.
- Split anything longer than one job takes: `python3 scripts/chunk_scene.py outputs/<slug>/<scene>` (default 55s for photo avatars; `--max 20 --video <take> --video-start <s>` for lip sync, which also cuts the matching footage).
- Upload: `create_media_upload` with the exact byte size and content type, then `bash scripts/upload.sh <file> "<upload_url>" <content type>` (must print 200). Photo: reuse `FISH_PHOTO_KEY` from `.env` if set, otherwise upload once and save the `object_key` there.
- `estimate_video_generation` for every job with the same inputs and parameters you'll render with. It's free, and it reports what Fish Audio detected (duration, size), which catches a wrong file.
- Show one table: job, seconds, credits, total, balance left afterwards. **Stop and wait for an explicit yes.** For anything big, offer to render one short piece first and look at it before spending the rest.

## 4. Render

- `generate_video` with exactly the estimated inputs and parameters, plus its `expected_credits`, `pricing_version`, and `idempotency_key` = `<slug>-<scene>-<chunk>-<audio file size in bytes>` so a retry can never charge twice. Submit independent jobs in one turn.
- Check them together with `get_generation_status`, waiting `poll_after_seconds` (about 60) between checks. A photo avatar takes about a minute per ten seconds; a 20 second 4K lip sync takes 3 to 6 minutes. A status of "stalled" is not a failure: keep polling. Never resubmit by yourself. Failed jobs refund automatically; tell the user.
- Download each result: `curl -sSL -o outputs/<slug>/<scene>/avatar.mp4 "<media.url>"` (or `chunks/NN.mp4` for a chunked scene). If the download fails, give the user the `view_url`.

## 5. Assemble

```bash
python3 scripts/assemble.py outputs/<slug>
```

Writes `outputs/<slug>/final.mp4` and `final.srt`, each scene exactly as long as its audio. Open it (`open` on a Mac), watch for anything off, and tell the user how long it is and what it cost (API dollars plus plan credits).

## Other jobs

### Faceless clip or voiceover

1. Write the narration (step 1) and voice it into `outputs/<slug>/narration` (step 2). A voiceover alone is done here: `audio.wav` plus `captions.srt` from `python3 scripts/captions.py`.
2. Footage: the user's own b-roll or stills, stock they have the rights to, or clips from Fish Audio's video models (`list_media_models` with capability `t2v`; quote and wait for a yes as usual; say "no text, no logos, no recognizable characters" in the prompt). No game, movie or TV footage they don't own.
3. `python3 scripts/faceless.py outputs/<slug>/narration <footage...> --out outputs/<slug>/final.mp4` (add `--vertical` for Shorts and Reels).

### Fix a flubbed line in a real take

The rest of the take stays real. Only the flubbed stretch is replaced.

1. Find the line: use the times the user gives, or `python3 scripts/transcribe.py <take> --find "<the words they said>"`.
2. `python3 scripts/fix_take.py prepare <take> --start <s> --end <s> --text "<corrected line, tags allowed>" --out outputs/fix-<slug>`. Set `--end` at the end of the pause after the flub: everything between start and end gets replaced. Play `line.wav` for the user next to the original.
3. Quote it. Lip sync on the real footage is the better-looking route: upload `clip.mp4` (`video/mp4`) and `line.wav` (`audio/wav`) with roles `sourceVideo` and `sourceAudio` on a `video_audio` model. The cheaper route is a photo avatar from a still of the same shot: `frame.jpg` (pass `--frame-at <s>` for a moment with the mouth closed, eyes on the lens) plus `line.wav` on an `avatar_audio` model. Wait for a yes.
4. Render, download to `outputs/fix-<slug>/synced.mp4`, then `python3 scripts/fix_take.py splice <take> outputs/fix-<slug>`. Open `compare.mp4` (before, then after) and `fixed.mp4` (the whole take). A cloned line right after their real voice is the hardest test there is: keep the direction calm and matter-of-fact.

### Cartoon skit or character dialogue

Read `reference/skit.md` first. Original characters only: no characters from shows, games or films.

## Rules

- `.env`, `me/` and `outputs/` stay local; they're gitignored. Never print the API key. Treat voice IDs like passwords: clones are created private for that reason, and the scripts save them to `.env` without printing them.
- Only clone the user's own voice, or one they have permission to use. Only put words in the mouth of the user's own face.
- Every Fish Audio step runs from here, through the scripts or the MCP. Don't send the user to the web app except to sign in, create an API key or add credit.
- Quote before every paid generation and wait for a yes. A yes covers the quote it answered, nothing else. Pilot one piece before a big batch.
- Measure before you guess. "Sounds deeper", "sounds off" and "sounds robotic" each have a script that puts a number on it.
