# The scripts from the video

These are the scene files behind the AI half of "I Let Claude Make a Video of Me Without Filming". Each one is the exact text that went to Drama 3, tags included. Swap in your own words and run them:

```bash
python3 scripts/fish_tts.py examples/video/04-hand-off.txt outputs/try/04-hand-off --takes 3
```

| File | What it shows |
|---|---|
| `01-cold-open.txt` | Two directions in one scene: fast and excited, then a deadpan beat. |
| `02-setup.txt` | A read that changes four times in 20 seconds, plus `<emphasis>` on one word. |
| `03-skit.txt` | Two voices in one generation. Speaker 0 is your clone, speaker 1 is a library voice. Short tags, one to three words each. Render it with `--temperature 0.15 --takes 6` (see below). |
| `04-hand-off.txt` | The mid-sentence whisper: `The filming. [voice drops to a whisper] Until today.` |
| `01-cold-open-es.txt` | The opener in Spanish with the same voice ID. Add `--language es`. |

## What it took to get these right

- **The whisper is a coin flip per take.** Same text, same settings, three takes: the whisper dropped 4.7 dB, 7.4 dB and 14.5 dB. Only the last one sounds like a whisper. That is why `--takes 3` exists: it measures the drop and keeps the best take.
- **The skit needed a lower temperature.** At 0.3 the two voices bled into each other in every take (the library voice sank toward the clone's pitch, the clone's first line got pulled up). At 0.15, two of six takes kept both voices in their own range. Roll six, let `voice_check.py` throw out the ones that bled, then pick by ear.
- **Short tags beat long ones in dialogue.** `[stressed, rushing]` works. A sentence-long stage direction made the second voice shrill in three of four takes. Want more expression? Add more short tags at the turns, not longer ones.
- **A comma instead of a full stop** between two short sentences ("I'm not guessing, I'm reading your transcripts") fixes a choppy, staccato read.
- **Strong acting tags change who it sounds like.** `[panicking]`, `[laughing]` and `[offended]` pushed the clone's pitch from about 108 Hz up to 124 to 148 Hz, which is a different-sounding person. Milder tags (`[tired, mumbling]`) stayed at 111 Hz. If your clone was made from calm clips, direct it calmly, or clone from clips that include the energy you plan to ask for.
- **Pick the second voice by ear, not by its description.** The first library voice chosen from its description got called robotic. The one that shipped was found by rendering the same skit with a dozen voices and listening.

The face in the video was not a photo avatar. It was a lip sync on a real take of Jason looking into the lens, rendered in chunks of about 20 seconds (`scripts/chunk_scene.py --video`). The process for both is in the skill.
