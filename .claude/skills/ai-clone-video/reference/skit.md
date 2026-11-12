# Cartoon skits and character dialogue

A dialogue scene acted out by cartoon characters. Original characters only: design your own, never characters from shows, games or films, and no real brands in frame.

There are two ways to make the shots talk. Decide first, because the audio comes from different places.

| | Drama 3 voices + lip sync | A video model that speaks |
|---|---|---|
| Voices | The user's clone and a library voice, one multi-speaker generation | Invented by the video model per clip, from a description |
| Sounds like the user | Yes | No |
| Steps per shot | keyframe image, then a talking-avatar job with that shot's audio | one image-to-video job with the line in the prompt |
| Cost seen | about 3,870 credits per second at 1080P | about 2,330 credits per second at 1080p |
| Use when | the skit is about the user's voice, or needs their clone | the look matters more than whose voice it is |

Either way, do these three things first.

## 1. Lock the set with one master image

Generating each shot's image separately re-arranges the room: characters swap sides of the desk, props move, a screen changes color. What works:

1. **Character sheets.** One image per character with an image `edit` model (the user's photo as the reference for their cartoon). Front and three-quarter view, mouth closed, plain background.
2. **One wide master shot** of the whole set at the highest resolution the model offers (4K), with both sheets as references. Write the layout left to right, say every face is fully visible and unobstructed, and keep everything inside the frame with space around it.
3. **Every other angle is a crop of the master.** Close-up on a character = punch in on that region. No reverse angles, nothing that needs a new view of the room.
4. **Pose changes are edits of the master** that change only one character ("same image, but he is now sitting upright, looking at the computer"), with that character's sheet passed as a second reference. Without the sheet, the edit redraws them as a different person.

Check every image before spending on video: both characters' pose and emotion (not just the speaker's), colors, and brands. Image models paint real logos on props unless told not to: "plain matte silver cans with no labels, no logos, no text and no printing of any kind" worked where "unbranded cans" did not.

Prompts that worked are in `examples/cartoon-skit/README.md`.

## 2. Pilot one shot

Make the first shot end to end and look at it before generating the rest. Every problem above showed up in shot one.

## 3. Quote everything

Images are cheap (roughly 900 to 2,000 credits each); the video adds up. Quote the whole batch, wait for a yes.

## Route A: Drama 3 voices, lip-synced per shot

1. Write the dialogue as a scene with `<|speaker:N|>` turns and mild, short directions (strong acting tags change how the clone sounds; see `voice.md`). Voice it with `--temperature 0.15 --takes 6`, then `python3 scripts/split_speakers.py outputs/<slug>/<scene>`.
2. `python3 scripts/skit.py split outputs/<slug>/<scene>` writes one audio clip per line into `shots/`.
3. For each line, quote a talking avatar (`avatar_audio`) with that shot's image as `ref` and `shotNN.wav` as `sourceAudio`, on a model that accepts a prompt. The prompt says who talks and who stays still:
   "Only the young man talks, his mouth moving in sync with the audio, slow tired blinks. The little computer on the right does not talk; its mouth stays closed. Static camera, everything else still."
4. Render, save each as `shots/shotNN.mp4`, then `python3 scripts/skit.py assemble outputs/<slug>/<scene>` cuts the shots on the exact turn boundaries over the original audio and writes `skit.mp4`.

The avatar model lip-syncs non-human faces fine (a cartoon face on a computer screen worked). It sometimes ignores "does not talk" for the silent character in the last second of a shot. The free fix is in the edit: cover the silent character with a still of itself from a clean frame; on a locked set the patch is invisible.

## Route B: a video model that speaks the lines

1. Pick an image-to-video model that generates audio (`list_media_models`, look for the `generated-audio` trait). Set the resolution yourself; these default to 480p.
2. One job per line, the shot's image as the start frame, and a prompt with the line in quotes plus a voice description:
   `The young man says, in a low, relaxed, slightly tired voice: "I haven't posted in nine days." He stays in the same low, relaxed register, never high-pitched. The computer only listens, mouth closed, does not speak. Lighting and colors stay exactly as in the image. Static camera.`
3. What we learned doing fourteen shots this way:
   - Every line came out word-perfect. Check anyway: `python3 scripts/transcribe.py shots/shot01.mp4`.
   - The voice is re-invented for each clip. The same description gave one character 131 to 145 Hz on calm lines and 170 to 208 Hz on excited ones. Add "stays in the same low, relaxed register, never high-pitched" and soften emotion words.
   - Describing light on a face ("the screen's glow on his face") changed colors (hair turned teal). Say "lighting and colors stay exactly as in the image".
   - In wide shots, say the other character "only listens, mouth closed, does not speak".
   - Clips come back at very different loudness (from -15 to -36 LUFS) and at a slow pace (about 140 words a minute, long pauses).
   - All clips render in parallel in a few minutes (about 40 seconds each).
4. `python3 scripts/tighten.py shots/shot*.mp4 --out outputs/<slug>/skit.mp4` trims the dead air, shortens the pauses, levels every clip and plays it at 1.15x. That took a 1:50 skit to 1:17 with every word intact, and the small jump cuts read as normal editing on a locked set.

## Camera lines that rendered as asked

- "Low-angle shot from desk level looking up at the little computer like a hero"
- "Over-the-shoulder shot from behind the computer: the back of its casing is soft and out of focus in the foreground on the left edge of the frame"
- "Extreme close-up: the computer's glowing screen fills almost the whole frame"
- Hiding the character who isn't talking: "far out of focus, slumped face-down on the desk so his face is hidden", "seen from the side so its screen is turned away from the camera", "heavily blurred and small at the very edge of the frame"

Use these as edits or crops of the master, not as fresh generations.
