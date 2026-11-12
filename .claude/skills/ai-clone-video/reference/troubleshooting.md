# Troubleshooting

Start with `python3 scripts/setup.py` (checks the account side) and `python3 scripts/selftest.py` (checks this machine). Then find the symptom.

## Setup and account

| Symptom | Cause | Fix |
|---|---|---|
| `Fish Audio returned 402` on a voice render | No API credit. The voice bills prepaid API credit, which is separate from the plan's credits. | Add a few dollars at https://fish.audio/app/developers/billing/. To test the pipeline with no credit, add `--model s2.1-pro-free` (a different, free model). |
| `Fish Audio returned 401` | The API key in `.env` is wrong or was deleted. | New key at https://fish.audio/app/api-keys, paste it into `.env`. |
| `Reference not found` on a render, or the voice "does not exist" | The voice ID belongs to a different Fish Audio account than the API key. | Check which account each side uses: `get_credit_balance` (the MCP sign-in) and `setup.py` (the API key). Sign in to the same account on both, then clone the voice again if needed. |
| No `mcp__fish-audio__` tools | Claude Code wasn't opened in this folder, the server wasn't approved, or it isn't signed in. | Open Claude Code in this folder, run `/mcp`, pick `fish-audio`, sign in. `claude mcp list` should show it as connected. If it isn't listed: `claude mcp add --transport http fish-audio https://api.fish.audio/mcp`. |
| The estimate says `can_generate: false` | Not enough plan credits, or the plan has no video (video needs Plus or higher). API credit does not pay for video. | Tell the user the balance and the price. Options: a shorter clip, 720P instead of 1080P, a cheaper model, the faceless route, or a higher plan. |
| The Fish Audio tools suddenly say to sign in again | `claude mcp remove fish-audio` (in any folder) or `claude mcp logout fish-audio` clears the sign-in everywhere: it is stored per server, not per folder. | `/mcp`, pick `fish-audio`, sign in again. |
| A balance or voice looks unfamiliar after signing in again | The MCP connection is tied to the team chosen at sign-in. | `/mcp`, sign in again and pick the right team. |
| `ffmpeg not found` | Not installed. | Mac: `brew install ffmpeg`. Windows: `winget install Gyan.FFmpeg`, then reopen the terminal. Linux: your package manager. |
| `python3` not found (Windows) | Windows installs Python as `python` or `py`. | Run the scripts with `python scripts/...`. |

## Voice

| Symptom | Cause | Fix |
|---|---|---|
| "It sounds deeper than me" | Usually loudness, not pitch: Fish Audio's output is about 4 dB hotter than a mic recording, and louder reads as deeper. Tags like `[deadpan]`, `[flat]`, `[confident, a little too smooth]` also ask for a lower read. | Measure first: `voice_check.py` on the render vs `voice_check.py --baseline` on their real clips. If the pitch matches, compare at equal loudness and drop the low-read tags. If it really is lower, lower `FISH_TEMPERATURE`. |
| "It sounds crunchy, like it's clipping" | Fish Audio's own limiter. | Keep `FISH_VOLUME_DB=-6` (or lower) and PCM format. Don't run the result through a loudness normalizer or compressor. |
| "It doesn't sound like me in this scene" (but did before) | Strong acting directions pushed the pitch up, or the take drifted. | `voice_check.py` on the scene. Soften the tags (`[tired]` instead of `[groaning into the desk]`), render `--takes 3`, pick the take nearest their normal pitch. Longer term: clone from clips that include that energy. |
| The second voice sounds like the user, or vice versa | The voices bled into each other in a multi-speaker pass. | `--temperature 0.15 --takes 6`; keep only takes where each speaker sits in its own range; pick a second voice far from the user's pitch. |
| The second voice changes into someone else mid-scene | Multi-speaker identity swap. | Another take. Only listening catches it. |
| The whisper isn't a whisper | Per-take luck: the drop ranged from 3 to 14 dB on identical text. | `--takes 3` keeps the deepest one. Or wrap the words in `<whisper>…</whisper>`. |
| A read is choppy, one sentence at a time | Full stops between short sentences. | Join them with a comma. |
| It sounds robotic | The voice, not the settings. | Audition other library voices on the same lines and pick by ear. Add short direction tags at each turn. |
| `WORD MISMATCH` | The model skipped, added or changed a word. | Render again. If it repeats on a number or a name, spell it the way it should be said. |
| A number or name is read wrong | Normalization. | Spell it out ("eighty three", "M C P"). |
| Renders come back empty, or `429` | Too many requests at once. | One at a time. `--takes` already does this. |
| `Invalid sample rate 48000` | PCM tops out at 44.1 kHz. | Leave the format alone; the scripts use 44.1 kHz. |

## Face

| Symptom | Cause | Fix |
|---|---|---|
| "This video is too large after optimization" at the estimate | A 4K clip with a high bitrate. | Use `chunk_scene.py --video` or re-encode to about 14 Mbps (`-crf 18 -maxrate 14M -bufsize 28M`). |
| A lip-sync job times out after about 15 minutes | Too long for one job (80 s of 4K did this). It refunds. | Chunks of 20 seconds: `chunk_scene.py --max 20 --video ...`. |
| Status says "stalled" | Long jobs flag this around 10 minutes and then finish. | Keep polling. Don't resubmit. |
| The avatar job is rejected for audio length | One photo-avatar job takes about 59 seconds. | `chunk_scene.py` (default 55 s), render each chunk, `assemble.py` joins them. |
| The avatar came out 360P or 480p | That model's default. | Read `get_media_model` and set `resolution` explicitly. |
| The avatar video is vertical (or horizontal) and shouldn't be | It copies the photo's shape. | Use a photo in the shape you want. |
| They look off to the side | Lip sync keeps the source footage's eyeline. | Use footage where they look into the lens. Check on full-size frames. |
| Jump cuts in the face | The source was stitched from separate stretches. | One continuous take (`chunk_scene.py --video`). |
| Both characters' mouths move | The model animated everyone in the image. | Prompt who talks and who stays still; patch the silent one with a still in the edit. |
| The last few frames are missing, or audio and video drift | Muxing with `-shortest`, or mixed frame rates. | Use `assemble.py`: it holds the last frame and cuts to the audio's exact length at the render's own frame rate. |
| The fixed line sounds pasted in | Digital silence under the new line, or an over-acted read. | `fix_take.py` lays the take's room tone under the line. Keep the direction calm; compare takes against their real line. |
| Captions are missing from the picture | Captions ship as `.srt` files next to the video, not burned in. | Upload the `.srt` to YouTube, or style it in an editor. |

## Images (skits)

| Symptom | Cause | Fix |
|---|---|---|
| Real brand logos on props | Image models add them. | "plain matte silver, no labels, no logos, no text and no printing of any kind", and check every image. |
| The room re-arranges between shots | Each image was generated separately. | One master image; crops and single-character edits of it. |
| A character looks like a different person after an edit | The edit had no reference for them. | Pass their character sheet as a second reference. |
| A color drifts (a screen turns green) | The close-up prompt didn't repeat the color. | Name the color in every prompt that shows it. |
| A background character has the wrong pose or mood | Only the speaker was described. | Describe every visible character's pose and emotion. |
