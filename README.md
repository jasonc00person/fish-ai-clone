# AI Clone

Make talking-head videos of yourself without filming. Claude Code writes the script, Fish Audio's Drama 3 model speaks it in your cloned voice, Fish Audio's avatar generation puts it on your face, and you get a finished video with captions. One prompt.

This is the repo from the video "I Let Claude Code and Fish Audio Make a Video of Me Without Filming". Every prompt and file used for the AI half of that video is in `examples/`.

## What you need

- **Claude Code**
- **A [Fish Audio](https://fish.audio) account.** The voice runs on the Drama 3 API, which bills per character (a 30-second script is about 500 characters, a fraction of a cent). Avatar videos need a plan with video (Plus or higher) and bill plan credits per second of audio.
- **ffmpeg and Python 3.** No pip installs. On a Mac: `brew install ffmpeg`.
- **One photo of you and 1 to 2 minutes of you talking.** An old video of yours works.

## Setup (once)

```bash
git clone <this repo> ai-clone && cd ai-clone
claude mcp add --transport http fish-audio https://api.fish.audio/mcp
cp .env.example .env
claude
```

Then, inside Claude Code:

1. Run `/mcp`, pick `fish-audio`, and sign in with your Fish Audio account.
2. Create an API key in your Fish Audio account and paste it into `.env` as `FISH_API_KEY`.
3. Put your photo at `me/photo.jpg`. Front-facing, mouth closed, looking at the lens. The avatar keeps the photo's shape: 16:9 for YouTube, 9:16 for Shorts and Reels.
4. Tell Claude: `set up my voice from <a link to one of your videos>`, or drop audio files of you talking into `me/`.

## Make a video

> make me a 30 second video telling my audience I'm going live on Thursday, and make it sound hyped

Claude writes the script with the emotion tags, renders your voice through Drama 3 with word timestamps, plays it for you, quotes the avatar credits and waits for your yes, renders your face, and assembles `outputs/<slug>/final.mp4` with `final.srt` captions. A 30-second clip takes a few minutes.

Two more things it does:

> I flubbed the line at 1:23 in take.mp4. It should say "it took me thirty minutes"

Your real footage stays. Claude voices the corrected line in your clone, lip-syncs just that stretch, and splices it back in, plus a before/after clip.

> make a 20 second faceless clip about why most AI content flops, over the clips in footage/

Your voice narrates over your b-roll (or footage it generates with Fish Audio's video models), vertical or horizontal, with captions.

> turn this argument between me and Claude into a cartoon skit

Two voices from one Drama 3 generation, cartoon characters that stay the same in every shot, and each line lip-synced onto its own keyframe.

## What's in here

| Path | What it does |
|---|---|
| `.claude/skills/ai-clone-video/SKILL.md` | The whole process, start to finish. Claude follows it. |
| `scripts/fish_tts.py` | Renders a scene through Drama 3 with word timestamps and checks every word against your script |
| `scripts/clone_voice.py` | Clones your voice (private) from a few clips plus their transcripts |
| `scripts/cut_clip.py` | Cuts clean voice clips out of any video or audio file |
| `scripts/split_speakers.py` | Splits a two-voice scene so only your lines go on your face |
| `scripts/upload.sh` | Uploads files to the slots the Fish Audio MCP hands out |
| `scripts/captions.py` | Builds captions from the word timestamps |
| `scripts/assemble.py` | Stitches the avatar clips, puts dialogue back together, writes the final video and captions |
| `scripts/fix_take.py` | Cuts a flubbed line out of a real take, voices the fix, and splices the lip-synced version back in |
| `scripts/faceless.py` | Lays your narration over background footage (16:9 or 9:16) with captions |
| `scripts/source_from_take.py` | Builds a lip-sync clip from your old footage, jump-cut on the pauses in the new audio |
| `scripts/skit.py` | Splits a dialogue scene into one clip per line and cuts the lip-synced cartoon shots back together |
| `examples/` | The exact Drama 3 text from the video, tags included |

Your `.env`, `me/` (voice clips, photo) and `outputs/` never leave your machine. They're gitignored.

## What we learned making the video

- **Clone from 1 to 2 minutes across 3 to 5 clips, with transcripts**, at the energy you want the clone to have. One 30-second clip works, but it sounds less like you.
- **Voice sounds deeper or smoother than you?** Lower `FISH_TEMPERATURE`. 0.3 matched best for us; the default is 0.7.
- **Sounds crunchy, like it's clipping?** Fish Audio renders hot enough to hit its own limiter. `FISH_VOLUME_DB=-6` renders it 6 dB quieter at the source, and the scripts level it back up cleanly.
- **Tags affect everything after them**, so you can change delivery mid-sentence: `And that's [voice drops to a whisper] the whole game.` Render it two or three times (a fraction of a cent each) and keep the take where the change lands hardest.
- **One avatar job takes about a minute of audio at most**, so longer scripts render scene by scene and get stitched back together.
- **Lip sync on your old footage beats a photo** for realism. Pick takes where you look straight into the lens: the model keeps your eyeline and head motion and only redoes your mouth.
- **Two characters in one shot? Tell the avatar model who talks.** Otherwise it can animate both faces.
- **Ask for blank props.** Image models drew real energy-drink logos on our cans until the prompt said "no labels, no logos".
