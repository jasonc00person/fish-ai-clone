# Voice: cloning, directing and checking Drama 3

Everything here was learned making the video. Numbers are from real renders.

## Cloning

- **1 to 2 minutes across 3 to 5 clips, each with its exact transcript.** A single 37 second clip with no transcript worked, but the second clone (about 2 minutes from the opening lines of five videos, with transcripts) was clearly closer. The opening lines of a video are usually the person at the energy they want the clone to have.
- **The clone only knows the energy it was cloned from.** Calm, explaining clips give a clone that sounds right calm and drifts when asked to panic or laugh. If the user wants hyped reads, include hyped clips.
- **Clean beats enhanced.** Leave Fish Audio's denoise off (`--enhance`) when the clips are clean: the plain clone kept more of the real tone. A quiet room is fine; music, a second voice or screen audio under the speech is not.
- **Fix the transcripts.** Automatic transcripts mishear brand names ("Krea" came back as "Cray AI"). Wrong transcripts teach wrong pronunciation.
- **Always private.** `clone_voice.py` creates private voices. The MCP's `create_voice_clone` makes them unlisted unless you pass `visibility: private`, and anyone holding an unlisted voice ID can use that voice. The MCP route also cannot send transcripts, so prefer the script.
- The API returns the voice ready to use immediately. Cloning is free.
- Fish Audio's "professional" clone (10 minutes or more of audio) is web-app only and has to be released publicly or unlisted, so it doesn't fit a private clone.

## The settings that made it sound right

These are the defaults in `.env.example`.

| Setting | Value | Why |
|---|---|---|
| Model | `drama-3` | The expressive one: takes plain-English direction, mid-sentence changes, multiple speakers. |
| `FISH_TEMPERATURE` | 0.3 (model default 0.7) | Lower sticks closer to the real voice. Tested 0.7, 0.5, 0.4, 0.3 by ear; 0.3 won. Tags still land at 0.3, a little softer. |
| `FISH_VOLUME_DB` | -6 | Fish Audio renders hot enough to hit its own limiter, which sounds crunchy, like clipping. Rendering 6 dB quieter at the source removes it. |
| Format | PCM, 44.1 kHz | Uncompressed. 44.1 kHz is the highest PCM rate; asking for 48 kHz returns a 400. |
| Leveling | plain gain to -20 LUFS | Done by `fish_tts.py`. Never a compressor or a one-pass loudness normalizer: those squash it right back. |

## Directing

- A `[direction]` affects everything after it until the next one. Put it exactly where the delivery should change, including mid-sentence: `The filming. [voice drops to a whisper] Until today.`
- **Short tags.** One to three words: `[stressed, rushing]`, `[defeated]`, `[teasing]`. Sentence-long stage directions made a library voice shrill in three of four takes. For more expression, add more short tags at the turns.
- **Tags change pitch.** `[confident, a little too smooth]`, `[deadpan]` and `[flat]` ask for a lower read and make the clone sound deeper than the person. `[panicking]`, `[laughing]`, `[offended]` pushed a clone from about 108 Hz to 124 to 148 Hz. `[casual]`, `[upbeat]`, `[tired, mumbling]` stayed in range.
- `<emphasis>word</emphasis>` makes the word longer, not louder (about 60% longer at temperature 0.3).
- `[beat]` and `[long pause]` make real pauses, up to about 1.4 seconds. `[laughing]` at the start of a line produces a real laugh in the gap before the first word.
- A whisper from a bracket direction is a coin flip per take (3 to 14 dB quieter on identical text). If it keeps coming out weak, wrap the words instead: `<whisper>Until today.</whisper>`.
- Tags count toward the bill, which is by UTF-8 byte. It is still fractions of a cent per scene.

## Picking takes

Takes differ, even at temperature 0.3: one line came out 4.9 seconds in one take and 6.2 in the next. Render several and choose.

1. `fish_tts.py --takes 3` (six for a two-voice scene). It renders one at a time on purpose: twelve at once got rate limited and half came back empty.
2. It measures each take and picks one: words must match the script, each speaker's pitch should sit within about 20% of that voice's normal pitch, and a whisper should drop 6 dB or more.
3. Then listen. Numbers throw takes out; ears pick the winner. Play the pick for the user, and if they want another, `--pick N`.

When the user judges whether it sounds like them:
- Put a real recording of them first in the lineup and say which one it is. People anchor on the real one; scores without it mean little.
- Match loudness between the real clip and the render. Fish Audio's output runs about 4 dB hotter than a typical mic recording, and louder reads as deeper and "better".
- Compare the same words with no tags when the question is likeness.

## Two voices in one scene

- Each turn starts with `<|speaker:N|>`. The voices come from `--speakers`, in order (default: the user's clone, then `FISH_CLAUDE_VOICE_ID`). A third speaker can reuse a voice: `--speakers FISH_VOICE_ID,FISH_CLAUDE_VOICE_ID,FISH_VOICE_ID` lets speaker 2 "steal" the user's voice.
- **Voices bleed.** In one pass with a clone at about 110 Hz and a library voice that sits at 240 to 263 Hz alone, the library voice landed at 109 to 172 Hz in most takes, and the clone's first line got pulled up to 135 to 166 Hz. At temperature 0.3, none of seven takes kept both voices in range. At 0.15, two of six did. So: `--temperature 0.15 --takes 6`.
- Save each voice's normal pitch so the checker can catch bleed: the clone's is saved at clone time; for the second voice, render one line with it alone (`--speakers FISH_CLAUDE_VOICE_ID` on a text with only `<|speaker:0|>`), run `voice_check.py --baseline` on that audio, and put the number in `FISH_CLAUDE_VOICE_PITCH_HZ`.
- A multi-speaker render can also swap the second voice's identity partway through. Only a listen catches that.
- **Choosing the second voice.** `search_voices` results are mostly community clones, including clones of real people: skip those. Voices by the "Fish Official" author are the safe ones. Descriptions don't predict how a voice performs with tags, so audition: render the same short dialogue with each candidate and listen. A voice chosen from its description came out robotic; the one that shipped was found by listening to a dozen. Pick one that sits well away from the user's pitch, or the two blur together.
- To replace one line without re-rendering the scene: render the line alone with the same `--speakers`, pick the take closest to the old pacing, and cut it in at the midpoints of the gaps on each side.

## Other languages

- Write the scene in the target language and pass `--language` (for example `es`, `es-MX`, `fr`). Same voice ID, same tags. Directions can stay in English.
- `<spanish>completamente gratis</spanish>` in the middle of an English sentence switched language for just those words. Language tags are experimental and vary by voice.

## What the API does (for debugging)

- `POST https://api.fish.audio/v1/tts/stream/with-timestamp`, headers `Authorization: Bearer <key>` and `model: drama-3`. A missing or misspelled `model` header does not fail: it silently falls back to another model.
- Body: `text`, `reference_id` (one voice ID, or a list for multi-speaker), `format`, `sample_rate`, `latency`, `temperature`, `prosody.volume`, `language`.
- The response is a server-sent event stream. Each event has an audio chunk and, sometimes, an alignment snapshot for a `chunk_seq`. A newer snapshot replaces the older one for that chunk. Word time on the full audio = segment time + `chunk_audio_offset_sec`.
- Timestamps are bare words: no punctuation, no tags. `scripts/align.py` matches them back to the script to recover who spoke, sentence ends and whispered stretches. That alignment drives the captions, the speaker split and the scene chunking.
- Billing: prepaid API credit, by UTF-8 byte. Drama 3 lists at $50 per million bytes; the launch price is $10. `s2.1-pro-free` is a free model for checking the pipeline without credit (it is not Drama 3 and reads tags differently).
- Check a key: `GET https://api.fish.audio/wallet/self/api-credit`.
- Transcription: `POST /v1/asr` with header `model: transcribe-1-pro`, about $0.36 per hour of audio (`scripts/transcribe.py`).
