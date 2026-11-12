# Face: photo avatar, lip sync on real footage, and the contract for paid jobs

Model names, prices and limits below were read from Fish Audio in November 2026. They change. Always call `list_media_models` and `get_media_model` and trust the live answer; use this file for what the live answer can't tell you (what looked good, what failed, how long things took).

## Which route

**Photo avatar** (`avatar_audio`): one photo plus the audio. The head moves and the mouth syncs; there are no hands and the body is still. Quick and needs no footage. It holds up in a short clip and gives itself away full-screen over minutes.

**Lip sync on real footage** (`video_audio`): a real take of the person plus the audio. The model keeps their real light, head motion and eyeline and only redraws the mouth. This looked far more real than any photo avatar and is what the video's AI half used. It needs footage.

Pick lip sync when the user has, or will record, a take of themselves looking into the lens. Otherwise the photo avatar.

## Photo avatar

- The output takes the photo's shape. A 16:9 photo gives a 16:9 video; a 9:16 photo gives a vertical one. There is no aspect setting on the default model.
- The photo: front-facing, mouth closed, eyes on the lens, even light, nothing in front of the face. A still pulled from their own 4K footage in their normal filming setup works well (`ffmpeg -ss <t> -i take.mp4 -frames:v 1 -q:v 2 me/photo.jpg`) and matches their other videos.
- Models (credits per second of audio):

| model_id | credits/s | notes |
|---|---|---|
| `creatify/aurora-v2/avatar` | 1,940 at 720P, 3,870 at 1080P | The default pick. `resolution` 480P / 720P / 1080P (default 720P). Audio 1 to 59.5 s, mp3 or wav. Billed per started second. Prompt optional. Output 1936x1080 at 24 fps for a 16:9 photo. About 1 minute for a 10 s clip. |
| `heygen/avatar4/avatar` | 3,549 | `resolution` defaults to 360P, so always set it. Has an `aspect_ratio` setting. No prompt. Failed once on the provider's side (refunded). |
| `veed/fabric-1.0/avatar` | 6,000 | 720P at most. |
| `infinitalk/avatar` | 8,000 | Prompt required. Audio up to about 29 s. |

- One job takes at most about 59 seconds of audio on the default model, which is why long scenes get split (`chunk_scene.py`, default 55 s).
- 1080P costs about double 720P. A 30 second scene is about 60,000 credits at 720P. A Plus plan has 250,000 a month, so quote before rendering and default to 720P unless they ask for more.
- **Two characters in one image:** pass a prompt that says who talks and who doesn't, or the model can animate both faces: "Only the man talks, his mouth moving in sync with the audio. The other character does not talk and stays still. Static camera." It still sometimes animates the silent one near the end of a shot.

## Lip sync on real footage

- Models (credits per second of the source video):

| model_id | credits/s | notes |
|---|---|---|
| `sync-lipsync/v3/lip-sync` | 4,177 | Best quality. Same price at 1080p and 4K, and returns the source's size and frame rate, frame for frame (3840x2160 at 23.976 came back identical in length). A 20 s 4K chunk takes 3 to 6 minutes. |
| `sync-lipsync/v2/pro/lip-sync` | 2,870 | Returns 1080p. About 4 minutes for 43 s; 80 s took 10.5 minutes. |
| `pixverse/lipsync/lip-sync` | 1,350 | Video up to 1920 px wide. |
| `veed/lipsync/lip-sync` | 450 | Fastest and cheapest (about 1.5 minutes for 24 s). Looked close to the mid tier in stills; in motion the top tier won. The result's URL ends in `.bin`; save it as `.mp4` and it plays. |

- These models take no parameters and no prompt: pass the two inputs (`sourceVideo`, `sourceAudio`) and nothing else.
- **Billing follows the video's length, not the audio's.** The source clip must be exactly as long as the audio. `chunk_scene.py --video` and `source_from_take.py` both cut it that way.
- **The footage decides the result.** The model keeps the eyeline, so if they were reading off to the side, the result looks off to the side. Check their eyes on full-size frames, not thumbnails.
- **One continuous take beats stitched pieces.** Stitching short lens-facing stretches from an old video (`source_from_take.py`) puts a jump cut at every join, and the jump cuts show. If the user can record: 2 to 5 minutes, one take, their normal filming setup and clothes, looking into the lens, talking naturally about anything at the energy of the script (not reading it), hands away from the face, a few closed-mouth pauses. Then every scene is cut from that take in order, and back-to-back scenes join with no jump.
- **Chunk it.** An 80 second 4K job timed out on the provider's side after about 15 minutes (fully refunded). The same footage in chunks of 22 seconds or less finished in 3 to 6.5 minutes each, first try. `chunk_scene.py --max 20 --video <take> --video-start <s>` cuts audio and footage together, on frame boundaries, at pauses. At 1080p, chunks up to about 45 seconds were fine.
- **File size.** 4K chunks of 87 to 120 MB were rejected at the estimate: "This video is too large after optimization." Re-encoded to about 14 Mbps (around 40 MB for 20 s) they pass. `chunk_scene.py` and `fix_take.py` already encode that way.
- If the script says things like "I didn't film this", the source take has to be old footage, not something shot for this video.

## Uploading

1. `create_media_upload` with `workspace_id`, `file_name`, the exact `file_size` in bytes (`python3 -c "import os,sys; print(os.path.getsize(sys.argv[1]))" <file>` works everywhere) and `content_type` (`image/jpeg`, `audio/wav`, `video/mp4`).
2. `bash scripts/upload.sh <file> "<upload_url>" <content type>`. It must print 200. The URL is signed for that exact size and type and expires in an hour.
3. Use the returned `object_key` as an input. A finished generation's `media.object_key` can be used directly as an input to the next job (an image result as the photo for an avatar, for example): never download and re-upload.
4. Cache the photo's `object_key` in `.env` as `FISH_PHOTO_KEY`.

## The quote and render contract

- `estimate_video_generation` is free. It returns the credits, the balance, `can_generate`, a `pricing_version`, and what Fish Audio detected for each input (duration, width, height). If `can_generate` is false, stop and tell the user why (usually not enough plan credits; API credit does not pay for video).
- Show the user the quote and wait for a yes that answers this quote.
- `generate_video` with the same inputs and parameters, `expected_credits` and `pricing_version` from the estimate, and an `idempotency_key` of your own (`<slug>-<scene>-<chunk>-<audio bytes>`). Credits are charged at submit. If the price changed, nothing is charged and you quote again.
- Poll with `get_generation_status` and all running `generation_ids` at once, waiting `poll_after_seconds` between calls (about 60 for video, 20 for images). Video jobs can run up to 2 hours before timing out, images 15 minutes. "stalled" appears around the 10 minute mark on long jobs that then finish.
- Never retry with a new idempotency key by yourself. A failed job refunds automatically; report it and ask.
- `media.url` is a permanent link anyone with it can open. `view_url` is the Fish Audio history page and only opens while that workspace is selected.

## Budget

- Plan credits pay for video and images. API credit (dollars) pays for the voice. They are separate wallets and one cannot cover the other. There are no credit top-up packs: when a plan's credits run out, the options are waiting for the monthly reset or a higher plan.
- Versions are what burn credits. Most of the credits this project used went to versions that were thrown away. Lock the script, approve the audio, pilot one clip, then render the rest.
- Rough sizes: 75 seconds of 4K lip sync on the top tier was about 314,000 credits. Thirty seconds of photo avatar at 720P is about 60,000.
