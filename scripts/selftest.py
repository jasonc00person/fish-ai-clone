#!/usr/bin/env python3
"""Check that every script works on this machine. Uses no credits and no network.

    python3 scripts/selftest.py

It fakes a voice render (tones where the words would be) and fake face videos
(test patterns), then runs the real scripts on them: captions, the pitch and
whisper check, speaker splitting, scene chunking, assembly, faceless clips, the
skit cutter, the footage stitcher, the line fixer and the tightener. If this
passes, ffmpeg and Python are set up right and anything that goes wrong later is
about your Fish Audio account, not this folder.
"""
import array
import json
import math
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import duration, require_ffmpeg, video_info  # noqa: E402

RATE = 44100
results = []


def run(script, *args):
    r = subprocess.run([sys.executable, str(HERE / script), *[str(a) for a in args]], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{script} failed:\n{r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *[str(a) for a in args]], check=True)


def fake_voice(scene, script, hz_by_speaker=(120.0,)):
    """Write audio.wav + words.json + scene.txt as if fish_tts.py had rendered `script`.

    `script` is a list of (speaker, word, seconds of pause after, whispered).
    """
    scene.mkdir(parents=True, exist_ok=True)
    samples, words, t = array.array("h"), [], 0.2
    samples.extend([0] * int(0.2 * RATE))
    for speaker, word, pause, quiet in script:
        length = 0.28
        hz, amp = hz_by_speaker[speaker], (1500 if quiet else 6000)
        for i in range(int(length * RATE)):
            phase = (i * hz / RATE) % 1.0
            samples.append(int(amp * (2 * phase - 1) * min(1.0, i / 400, (length * RATE - i) / 400)))
        words.append({"text": word.strip(".,?!"), "start": round(t, 3), "end": round(t + length, 3), "chunk": 0})
        t += length
        samples.extend([0] * int(pause * RATE))
        t += pause
    with wave.open(str(scene / "audio.wav"), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(samples.tobytes())
    text, last, was_quiet = "", None, False
    for speaker, word, _, quiet in script:
        if len(hz_by_speaker) > 1 and speaker != last:
            text += f"\n<|speaker:{speaker}|>[calm] "
            was_quiet = False
        if quiet != was_quiet:
            text += "[voice drops to a whisper] " if quiet else "[back to normal] "
            was_quiet = quiet
        text += word + " "
        last = speaker
    (scene / "scene.txt").write_text(text.strip() + "\n")
    (scene / "words.json").write_text(json.dumps(words))
    (scene / "meta.json").write_text(json.dumps({"text_file": str(scene / "scene.txt")}))
    return duration(scene / "audio.wav")


def fake_video(path, seconds, fps="24", size="320x180", audio=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    src = ["-f", "lavfi", "-i", f"testsrc=s={size}:r={fps}:d={seconds:.3f}"]
    if audio:
        # One second of tone, half a second of silence, repeating: something with pauses to trim.
        src += ["-f", "lavfi", "-i", f"sine=f=150:d={seconds:.3f},volume='if(lt(mod(t,1.5),1),1,0)':eval=frame"]
    ff(*src, "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
       *(["-c:a", "aac", "-shortest"] if audio else []), path)


def sentence(n, speaker=0, start=0):
    """n filler words, a sentence break every 6 words (longer pause there)."""
    out = []
    for i in range(start, start + n):
        end = (i + 1) % 6 == 0
        out.append((speaker, f"word{i}" + ("." if end else ""), 0.5 if end else 0.06, False))
    return out


def test(name):
    def wrap(fn):
        try:
            fn()
            results.append((name, None))
            print(f"  pass  {name}")
        except Exception as e:  # report every failure, not just the first
            results.append((name, e))
            print(f"  FAIL  {name}: {e}")
        return fn
    return wrap


def close(a, b, tol, what):
    if abs(a - b) > tol:
        raise AssertionError(f"{what}: expected about {b:.2f}, got {a:.2f}")


def main():
    require_ffmpeg()
    print("AI Clone self-test (no credits, no network)")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        @test("captions carry the script's punctuation")
        def _():
            scene = tmp / "cap" / "01"
            fake_voice(scene, sentence(12))
            run("captions.py", scene)
            srt = (scene / "captions.srt").read_text()
            assert "word5." in srt and "-->" in srt, srt[:200]

        @test("pitch and whisper check")
        def _():
            scene = tmp / "vc" / "01"
            fake_voice(scene, sentence(12) + [(0, "quiet", 0.06, True), (0, "words.", 0.3, True)])
            report = json.loads(run("voice_check.py", scene, "--json"))[0]
            close(report["pitch_by_speaker"]["0"], 120.0, 6.0, "pitch")
            close(report["whispers"][0]["drop_db"], 12.0, 3.0, "whisper drop")

        @test("long scene splits at sentence breaks and assembles to the audio's exact length")
        def _():
            project = tmp / "long"
            scene = project / "01-main"
            total = fake_voice(scene, sentence(180))
            run("chunk_scene.py", scene, "--max", "30")
            plan = json.loads((scene / "chunks.json").read_text())["chunks"]
            assert len(plan) >= 3 and all(c["end"] - c["start"] <= 30.01 for c in plan), plan
            close(sum(c["end"] - c["start"] for c in plan), total, 0.02, "chunk total")
            for c in plan:  # every cut should sit in a sentence pause, not mid-phrase
                if c["end"] < total - 0.01:
                    words = json.loads((scene / "words.json").read_text())
                    gap = min(abs(c["end"] - (a["end"] + b["start"]) / 2) for a, b in zip(words, words[1:])
                              if b["start"] - a["end"] > 0.4)
                    assert gap < 0.01, f"cut at {c['end']} is not in a sentence pause"
                fake_video(scene / c["video"], c["end"] - c["start"] - 0.1)  # a few frames short, like real renders
            run("assemble.py", project)
            close(duration(project / "final.mp4"), total, 0.06, "final length")
            assert video_info(project / "final.mp4")[3] == 24.0
            assert (project / "final.srt").read_text().count("-->") > 10

        @test("dialogue: only your lines go on your face")
        def _():
            project = tmp / "dialogue"
            scene = project / "01-skit"
            script = sentence(6, 0) + sentence(6, 1, 6) + sentence(6, 0, 12) + sentence(6, 1, 18)
            total = fake_voice(scene, script, hz_by_speaker=(110.0, 230.0))
            out = run("split_speakers.py", scene)
            turns = json.loads((scene / "turns.json").read_text())
            assert [t["speaker"] for t in turns] == [0, 1, 0, 1], out
            mine = duration(scene / "speaker0-only.wav")
            assert total * 0.3 < mine < total * 0.7, f"speaker 0 audio is {mine:.1f}s of {total:.1f}s"
            report = json.loads(run("voice_check.py", scene, "--json", "--expect", "0=110,1=230"))[0]
            assert not report["flags"], report["flags"]
            fake_video(scene / "avatar.mp4", mine)
            run("assemble.py", project)
            close(duration(project / "final.mp4"), total, 0.06, "final length")

        @test("lip-sync chunks from one continuous take are frame-exact")
        def _():
            scene = tmp / "sync" / "01"
            total = fake_voice(scene, sentence(60))
            take = tmp / "sync" / "take.mp4"
            fake_video(take, total + 8, fps="30000/1001")
            run("chunk_scene.py", scene, "--max", "12", "--video", take, "--video-start", "2.5")
            plan = json.loads((scene / "chunks.json").read_text())["chunks"]
            assert len(plan) >= 2
            for c in plan:
                clip, wav = scene / c["source"], scene / c["audio"]
                close(duration(clip), duration(wav), 0.04, f"chunk {c['n']} footage vs audio")
            close(sum(c["frames"] for c in plan) / (30000 / 1001), total, 0.04, "frames total")

        @test("skit: one shot per line, cut back together")
        def _():
            scene = tmp / "skit" / "01"
            total = fake_voice(scene, sentence(6, 0) + sentence(6, 1, 6) + sentence(6, 0, 12), hz_by_speaker=(110.0, 230.0))
            run("split_speakers.py", scene)
            run("skit.py", "split", scene)
            shots = sorted((scene / "shots").glob("shot*.wav"))
            assert len(shots) == 3
            for s in shots:
                fake_video(s.with_suffix(".mp4"), duration(s), fps="24", size="484x270")
            run("skit.py", "assemble", scene, "--size", "320x180")
            close(duration(scene / "skit.mp4"), total, 0.06, "skit length")

        @test("faceless clip over footage and a still")
        def _():
            narr = tmp / "faceless" / "narration"
            total = fake_voice(narr, sentence(18))
            a, b, still = tmp / "faceless" / "a.mp4", tmp / "faceless" / "b.mp4", tmp / "faceless" / "c.jpg"
            fake_video(a, 3)
            fake_video(b, 2, size="180x320")
            ff("-f", "lavfi", "-i", "testsrc=s=320x180:d=1", "-frames:v", "1", still)
            out = tmp / "faceless" / "final.mp4"
            run("faceless.py", narr, a, b, still, "--out", out, "--vertical")
            close(duration(out), total, 0.06, "faceless length")
            assert video_info(out)[:2] == (1080, 1920)
            assert out.with_suffix(".srt").exists()

        @test("footage stitcher refuses to repeat shots silently")
        def _():
            scene = tmp / "stitch" / "01"
            total = fake_voice(scene, sentence(24))
            take = tmp / "stitch" / "take.mp4"
            fake_video(take, 40)
            out = tmp / "stitch" / "source.mp4"
            run("source_from_take.py", take, scene, "--ranges", "1-9,12-20,22-39", "--out", out, "--height", "180")
            close(duration(out), total, 0.06, "source length")
            try:
                run("source_from_take.py", take, scene, "--ranges", "1-3", "--out", out, "--height", "180")
            except RuntimeError as e:
                assert "add up to" in str(e)
            else:
                raise AssertionError("ranges shorter than the audio should stop with a message")

        @test("line fix splices back into the take")
        def _():
            fix = tmp / "fix"
            fix.mkdir()
            take = fix / "take.mp4"
            fake_video(take, 12, audio=True)
            start, end = 4.0, 7.0
            ff("-f", "lavfi", "-i", "sine=f=180:d=3", "-ar", "48000", "-ac", "1", fix / "line.wav")
            ff("-f", "lavfi", "-i", "anoisesrc=d=0.5:a=0.002", "-ar", "48000", "-ac", "1", fix / "room.wav")
            fake_video(fix / "synced.mp4", 3)
            ff("-ss", start, "-to", end, "-i", take, "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", fix / "original.mp4")
            (fix / "fix.json").write_text(json.dumps({"take": str(take), "start": start, "end": end}))
            run("fix_take.py", "splice", take, fix)
            close(duration(fix / "fixed.mp4"), 12.0, 0.1, "fixed take length")
            close(duration(fix / "compare.mp4"), 6.6, 0.15, "before/after length")

        @test("tightener trims pauses and levels")
        def _():
            a, b = tmp / "tight" / "a.mp4", tmp / "tight" / "b.mp4"
            fake_video(a, 6, audio=True)
            fake_video(b, 4.5, audio=True)
            out = tmp / "tight" / "out.mp4"
            run("tighten.py", a, b, "--out", out)
            assert duration(out) < 9.0, f"expected well under 10.5s, got {duration(out):.1f}s"

        @test("setup status runs")
        def _():
            assert "AI Clone" in run("setup.py", "--hook")

    failed = [(n, e) for n, e in results if e]
    print(f"\n{len(results) - len(failed)} of {len(results)} passed.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
