# AI Clone

Make talking-head videos of yourself without filming. Claude Code writes the script, Fish Audio's Drama 3 model speaks it in your cloned voice, Fish Audio's avatar generation puts it on your face, and you get a finished video with captions. One prompt.

This is the repo from the video [I Let Claude Make a Video of Me Without Filming](https://youtu.be/vQroJu0Vaqg). The scripts behind the AI half of that video are in [`examples/video/`](examples/video/), tags and all.

## What you need

- **[Claude Code](https://claude.com/claude-code)**, in the terminal or the desktop app.
- **A [Fish Audio](https://fish.audio/?fpr=v34eet) account.** Two separate wallets live in it:
  - **API credit** pays for the voice (the Drama 3 API). It's prepaid dollars, and a 30 second script costs well under a cent. A few dollars lasts a long time.
  - **A plan with video (Plus or higher)** pays for the face. Avatar and lip-sync jobs bill plan credits per second. You don't need a plan for faceless clips or voiceovers.
- **ffmpeg and Python 3.** No pip installs. On a Mac: `brew install ffmpeg`.
- **1 to 2 minutes of you talking**, from any video you already have. For a face: one photo of you, or a take of you looking into the camera.

Signing up through [this link](https://fish.audio/?fpr=v34eet) gets you 10,000 free web app credits, and for a limited time the Drama 3 API is 80% off and creator plans are 50% off. Fish Audio sponsored the video, and that's an affiliate link.

## Setup

**The easy way.** Open Claude Code, paste this repo's link, and say:

> set this up and set up the Fish Audio MCP

Claude clones the repo, runs the setup check and walks you through the rest. You do three things yourself: sign in to Fish Audio when the browser opens, paste an API key into a file, and (once) open Claude Code inside the new folder.

**By hand.**

```bash
git clone https://github.com/jasonc00person/fish-ai-clone.git
cd fish-ai-clone
python3 scripts/setup.py
claude
```

`setup.py` creates your `.env`, registers the Fish Audio connection with Claude Code, and tells you exactly what is still missing. Then, inside Claude Code:

1. Run `/mcp`, pick `fish-audio`, and sign in with your Fish Audio account.
2. Create an API key at [fish.audio/app/api-keys](https://fish.audio/app/api-keys), paste it into `.env` after `FISH_API_KEY=`, and add a few dollars of API credit.
3. Tell Claude: `set up my voice from <a video file of you talking, or a link to one of your videos>`.
4. For a photo avatar, put a photo at `me/photo.jpg`: front-facing, mouth closed, looking at the lens. The video keeps the photo's shape, so 16:9 for YouTube and 9:16 for Shorts and Reels.

Run `python3 scripts/setup.py` any time to see where you stand, and `python3 scripts/selftest.py` to check that everything works on your machine without spending a credit.

## Make a video

> make me a 30 second video telling my audience I'm going live on Thursday, and make it sound hyped

Claude writes the script with the emotion tags, renders a few takes of your voice through Drama 3 and keeps the best one, plays it for you, quotes the face render and waits for your yes, renders it, and assembles `outputs/<slug>/final.mp4` with `final.srt` captions. A 30 second clip takes a few minutes.

More things to ask for:

> make a 20 second faceless clip about why most AI content flops, over the clips in footage/

Your voice over your b-roll or stills (or footage it generates), vertical or horizontal, with captions.

> I flubbed the line at 1:23 in take.mp4. It should say "it took me thirty minutes"

Your real footage stays. Claude voices the corrected line in your clone, lip-syncs just that stretch, and splices it back in with a before/after clip.

> make this video again in Spanish

Same voice, same delivery tags, another language.

> use my footage instead of a photo: me/take.mp4

Lip sync on a real take of you looking into the lens. This is the most realistic route and the one the video used.

> turn this argument between me and Claude into a cartoon skit

Two voices from one Drama 3 generation, and cartoon characters that stay the same in every shot.

## What it costs

- **Voice:** Drama 3 bills by the character. The whole AI half of the video was about 4,500 characters, which came to about four and a half cents at the launch price.
- **Face:** plan credits per second of video. As a guide, 30 seconds of photo avatar at 720P is about 60,000 credits and 20 seconds of top-quality lip sync is about 84,000. A Plus plan has 250,000 a month.
- **Nothing charges without a yes.** Every face render is quoted first, and a failed render gives the credits back.

## What's in here

- `.claude/skills/ai-clone-video/`: the whole process, start to finish, plus the notes on voice, face, skits and troubleshooting. Claude follows it.
- `scripts/setup.py`: sets the project up and reports what's missing
- `scripts/selftest.py`: checks every script on your machine, no credits used
- `scripts/voice_samples.py`: finds clean clips of you talking in footage you already have and transcribes them
- `scripts/clone_voice.py`: clones your voice (private) and saves it to `.env`
- `scripts/fish_tts.py`: renders a scene through Drama 3 with word timestamps, checks every word against your script, renders several takes and keeps the best
- `scripts/voice_check.py`: measures a render's pitch per speaker and how far a whisper drops, so "does it sound like me" has a number
- `scripts/split_speakers.py`: splits a two-voice scene so only your lines go on your face
- `scripts/chunk_scene.py`: cuts a long scene at sentence breaks (and cuts matching footage for lip sync)
- `scripts/assemble.py`: joins the face clips, lays the clean audio back on, writes the final video and captions
- `scripts/captions.py`: builds captions from the word timestamps
- `scripts/faceless.py`: narration over background footage, 16:9 or 9:16
- `scripts/fix_take.py`: replaces a flubbed line in a real take
- `scripts/transcribe.py`: transcribes any file with a time for every word, and finds a line in it
- `scripts/source_from_take.py`: builds a lip-sync clip from the moments in old footage where you look at the lens
- `scripts/skit.py` and `scripts/tighten.py`: cut cartoon skit shots together and tighten their pacing
- `scripts/upload.sh`: uploads files to the slots the Fish Audio MCP hands out
- `examples/`: the scripts from the video, a faceless narration, and the cartoon skit prompts

Your `.env`, `me/` (voice clips, photo, footage) and `outputs/` never leave your machine. They're gitignored. Your voice is cloned as private, and the scripts never print your voice ID or API key.

## What we learned making the video

- **Clone from 1 to 2 minutes across 3 to 5 clips, with transcripts**, at the energy you want the clone to have. One 30 second clip works, but it sounds less like you.
- **Temperature 0.3, volume -6 dB, PCM.** Lower temperature sticks closer to your real voice (the default is 0.7). Rendering 6 dB quieter keeps Fish Audio off its own limiter, which is what causes that crunchy, clipped sound. These are the defaults here.
- **"It sounds deeper than me" is usually loudness.** We measured it: the pitch matched, the render was just 4 dB louder. Compare at the same volume before changing anything.
- **Tags affect everything after them**, so you can change delivery mid-sentence: `And that's [voice drops to a whisper] the whole game.`
- **Render three takes.** The same whisper line dropped 5, 7 and 14 dB across three takes, and only one of those sounds like a whisper. Takes cost a fraction of a cent, so the scripts render several and keep the best.
- **Big acting tags change who it sounds like.** `[panicking]` and `[laughing]` pushed the clone's pitch way off. Short, mild tags kept it sounding like the same person.
- **Two voices in one scene bleed into each other.** Dropping the temperature to 0.15 and rolling six takes fixed it.
- **Pick voices by ear, not by description.** The library voice that shipped was found by listening to a dozen on the same lines.
- **Lip sync on real footage beats a photo** for realism. Use one continuous take where you look straight into the lens: the model keeps your eyeline and head motion and only redoes your mouth. Stitched clips show their jump cuts.
- **Render lip sync in 20 second chunks.** A single 80 second 4K job timed out. Chunks cut at pauses joined back with no visible seam.
- **One avatar job takes about a minute of audio**, so longer scripts are split at sentence breaks using the word timestamps and stitched back together.
- **Lock the script before you render a face.** Voice takes are nearly free. Face renders are where the credits go, and every rewrite means paying again.
- **For cartoon skits, make one master image of the set** and build every shot from crops and small edits of it. Generating each shot separately re-arranges the room.
- **Ask for blank props.** Image models drew real energy-drink logos on our cans until the prompt said "no labels, no logos, no printing of any kind".

Something not working? `.claude/skills/ai-clone-video/reference/troubleshooting.md` lists every problem we hit and the fix, or just tell Claude what went wrong.
