# Cartoon skit: the prompts that worked

`skit.txt` is a two-character dialogue with three voices in one Drama 3 generation: speaker 0 is your clone, speaker 1 is a library voice, and speaker 2 is your clone again, so the second character can "steal" your voice for one line:

```bash
python3 scripts/fish_tts.py examples/cartoon-skit/skit.txt outputs/skit/01 \
    --speakers FISH_VOICE_ID,FISH_CLAUDE_VOICE_ID,FISH_VOICE_ID --temperature 0.15 --takes 6
```

The process is in `.claude/skills/ai-clone-video/reference/skit.md`. These are the image and video prompts from our build, as written. The characters were a cartoon version of the creator and a small retro computer with a face on its screen. Swap in your own.

## Character sheets

**You, as a cartoon** (image edit, your photo as the reference, 2K, 16:9):

> Character design sheet of this exact man as a 3D animated feature-film cartoon character: keep his face shape, eyes, eyebrows, messy dark swept hair and plain black t-shirt so he is clearly recognizable, with slightly stylized proportions (bigger eyes, softer features). Front view and three-quarter view, full upper body, neutral friendly expression with mouth closed. Plain light gray background, soft studio lighting, no text, no logos.

**The second character** (text to image, 2K):

> Character design sheet, 3D animated feature-film style: a tiny retro beige CRT desktop computer with a chunky keyboard, its curved glass screen shows a simple friendly glowing face (two oval eyes, expressive mouth) in warm orange. Front view and three-quarter view on a plain light gray background. Soft studio lighting, no text, no logos.

To put a specific mark or symbol on a character, pass it as a second reference image and say so: "its screen face is the symbol from reference 2, in that exact color, with two simple cartoon eyes and a small mouth so it can talk."

## The master shot

One wide image of the whole set at 4K, with both sheets (and a mood image, if you have one) as references. Everything else is a crop or a single-character edit of this image.

> References: image 1 is the cartoon young man (keep his exact face, black hair, black t-shirt and 3D animated style). Image 2 is a small beige retro CRT computer whose screen face has two round eyes and a small smile (keep that exact design). Image 3 is the bedroom set, lighting and render style to match.
>
> Create ONE wide master shot of a locked set in a 3D animated feature-film style. Bedroom at night: warm light from the desk lamp, an orange glow from the CRT screen, cool blue moonlight through a window.
>
> Camera at desk height, looking at the desk from the front. Layout from left to right:
> - Left: the young man in a black office chair, slumped forward over the desk, his cheek resting flat on the desktop and his head turned so his whole face points straight at the camera. His face is fully visible and unobstructed: tired half-open eyes, mouth relaxed and slightly open, nothing in front of his mouth or chin. His arms rest on the desk.
> - Middle: an open dark gray laptop on the desk, angled toward him, low enough that it does not cover any part of his face.
> - Right of the laptop: the small beige CRT computer with its beige keyboard, screen facing the camera, its face fully visible, eyes just opening.
> - Far right: a black desk lamp on the desk, its shade lit.
> - Behind: an unmade bed against the back wall, a bookshelf, and a window with night sky.
> - On the desk: a scatter of empty drink cans that are plain matte silver with no labels, no logos, no text and no printing of any kind, plus a few crumpled papers and a cable.
>
> Keep the whole desk, both characters and the lamp inside the frame with some space around them. No text, no logos and no brand names anywhere in the image.

Why it's written this way:
- "Layout from left to right" pins where everything sits, so crops are predictable.
- "Fully visible and unobstructed... nothing in front of his mouth" matters because the mouth is what gets animated.
- The cans line is that long because "unbranded cans" produced a real energy-drink logo.

## Making a shot talk (Drama 3 audio, lip-synced)

Talking-avatar job, the shot's image as the photo, that line's audio, and a prompt:

> Only the young man talks: he groans the line with his cheek resting on the desk, his mouth moving in sync with the audio, slow tired blinks, slight head roll. The little computer on the right does not talk; its face just blinks awake once and its mouth stays closed. Static camera, everything else still.

> Only the little computer talks: its screen face speaks the line calmly and a little smug, its small cartoon mouth moving in sync with the audio, eyes blinking. The young man in the background stays still. Static camera.

The pattern: "Only X talks... Y does not talk and stays still... Static camera."

## Making a shot talk (the video model speaks)

Image to video on a model that generates audio, the shot's image as the start frame:

> The young man says, in a low, relaxed, slightly tired voice: "I haven't posted in nine days. I have zero ideas." He stays in the same low, relaxed register, never high-pitched. The little computer only listens, mouth closed, does not speak. Lighting and colors stay exactly as in the image. Static camera.

Then `python3 scripts/tighten.py shots/shot*.mp4 --out skit.mp4`.

## B-roll for a faceless clip

Text to video, 10 seconds each. Described as a look, with no game or show named:

> Third-person chase camera behind a stylized runner sprinting across neon-lit city rooftops at night, vaulting over vents and leaping gaps, smooth fast motion like an arcade runner game, saturated colors, no text, no logos, no recognizable characters.

> Fast aerial whip: the camera rockets up from a city street to a top-down satellite view, zips across the rooftops of a sunny city, then dives straight down through the roof of an apartment building. Motion blur.

Generated clips often go strange in the last half second. Cut a little early.
