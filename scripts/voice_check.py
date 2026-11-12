#!/usr/bin/env python3
"""Measure a voice render instead of guessing: pitch per speaker turn, and how far a whisper drops.

    python3 scripts/voice_check.py outputs/my-video/01-hook              # a scene folder from fish_tts.py
    python3 scripts/voice_check.py outputs/my-video/01-hook/takes/*      # compare takes side by side
    python3 scripts/voice_check.py --baseline me/voice/*.wav             # your real pitch, from your own clips

Why this exists: the same voice ID does not always sound like the same person.
Strong acting directions ([panicking], [laughing]) pull a clone's pitch up, and in
a two-voice scene the voices can bleed toward each other. Both show up as numbers
before they show up as "that doesn't sound like me". A take is good when each
speaker's pitch sits near that voice's normal pitch (FISH_VOICE_PITCH_HZ and
FISH_CLAUDE_VOICE_PITCH_HZ in .env, within about 20 percent) and any whispered
words land clearly quieter than the rest (6 dB or more reads as a real whisper).

Then listen. The numbers rule takes out; your ears pick the winner.

Standard library only, plus ffmpeg on your PATH.
"""
import argparse
import array
import json
import math
import os
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from align import align, turns  # noqa: E402
from common import load_env, require_ffmpeg  # noqa: E402

SR = 8000
FMIN, FMAX = 65, 420
TOLERANCE = 0.20  # a turn further than this from the voice's normal pitch gets flagged


def samples(path, start=None, end=None):
    cmd = ["ffmpeg", "-v", "error", "-nostdin"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    if end is not None:
        cmd += ["-to", f"{end:.3f}"]
    cmd += ["-i", str(path), "-af", "highpass=f=60,lowpass=f=1000", "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"]
    return array.array("h", subprocess.run(cmd, capture_output=True, check=True).stdout)


def pitch_track(x):
    """F0 in Hz for every voiced 40 ms frame (autocorrelation, coarse at 4 kHz then refined at 8 kHz)."""
    n = 320
    if len(x) < n * 3:
        return []
    frames = [x[i:i + n] for i in range(0, len(x) - n, n // 2)]
    energies = [sum(v * v for v in f) for f in frames]
    loud = sorted(energies)[int(len(energies) * 0.9)]
    gate = max(loud * 0.02, n * 60.0 ** 2)
    lo, hi = SR // FMAX, SR // FMIN
    out = []
    for frame, energy in zip(frames, energies):
        if energy < gate:
            continue
        half = frame[::2]
        m = len(half)
        coarse = {}
        for lag in range(lo // 2, hi // 2 + 1):
            coarse[lag] = sum(half[j] * half[j + lag] for j in range(m - lag)) * m / (m - lag)
        best = max(coarse.values())
        if best <= 0.3 * (energy / 2):
            continue
        # The shortest lag that is nearly as strong as the best one: avoids landing an octave low.
        pick = next(lag for lag in sorted(coarse) if coarse[lag] >= 0.85 * best
                    and coarse[lag] >= coarse.get(lag - 1, -1e30) and coarse[lag] >= coarse.get(lag + 1, -1e30))
        fine = {}
        for lag in range(max(lo, pick * 2 - 2), min(hi, pick * 2 + 2) + 1):
            fine[lag] = sum(frame[j] * frame[j + lag] for j in range(n - lag)) * n / (n - lag)
        lag = max(fine, key=fine.get)
        if fine[lag] < 0.45 * energy:
            continue
        a, b, c = fine.get(lag - 1), fine[lag], fine.get(lag + 1)
        shift = 0.0
        if a is not None and c is not None and (a - 2 * b + c) != 0:
            shift = max(-0.5, min(0.5, 0.5 * (a - c) / (a - 2 * b + c)))
        out.append(SR / (lag + shift))
    return out


def median_pitch(path, start=None, end=None):
    """Median F0 in Hz, or None when there is too little voiced audio to say."""
    track = pitch_track(samples(path, start, end))
    return round(statistics.median(track), 1) if len(track) >= 8 else None


def rms_db(path, spans):
    """RMS level in dBFS over a list of (start, end) spans."""
    total, count = 0.0, 0
    for a, b in spans:
        if b - a < 0.05:
            continue
        cmd = ["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(path),
               "-f", "s16le", "-ac", "1", "-ar", "16000", "-"]
        x = array.array("h", subprocess.run(cmd, capture_output=True, check=True).stdout)
        total += sum(v * v for v in x)
        count += len(x)
    if not count or not total:
        return None
    return 10 * math.log10(total / count / 32768.0 ** 2)


def check(scene, text=None, expect=None):
    """Measure one rendered scene folder. Returns a dict; 'flags' lists anything worth a re-render."""
    scene = Path(scene)
    audio = scene / "audio.wav"
    words = json.loads((scene / "words.json").read_text())
    if text is None:
        meta = json.loads((scene / "meta.json").read_text()) if (scene / "meta.json").exists() else {}
        source = Path(meta.get("text_file", ""))
        for candidate in (scene / "scene.txt", source, Path(__file__).resolve().parent.parent / source):
            if candidate.is_file():
                text = candidate.read_text()
                break
    aligned = align(text or "", words)
    expect = expect or {}
    report = {"scene": str(scene), "turns": [], "flags": []}

    for t in turns(aligned):
        hz = median_pitch(audio, t["start"], t["end"])
        row = {"speaker": t["speaker"], "start": t["start"], "end": t["end"], "pitch_hz": hz, "text": t["text"][:60]}
        want = expect.get(t["speaker"])
        if hz and want:
            row["off_pct"] = round((hz / want - 1) * 100)
            if abs(hz / want - 1) > TOLERANCE:
                report["flags"].append(f"speaker {t['speaker']} at {t['start']:.1f}s is {hz:.0f} Hz, "
                                       f"{abs(row['off_pct'])}% {'above' if hz > want else 'below'} its normal {want:.0f} Hz")
        report["turns"].append(row)

    by_speaker = {}
    for row in report["turns"]:
        if row["pitch_hz"]:
            by_speaker.setdefault(row["speaker"], []).append(row["pitch_hz"])
    report["pitch_by_speaker"] = {s: round(statistics.median(v), 1) for s, v in by_speaker.items()}
    if len(by_speaker) > 1 and not expect:
        meds = sorted(report["pitch_by_speaker"].values())
        if meds[-1] / meds[0] < 1.15:
            report["flags"].append("the speakers sit within 15% of each other in pitch; check they still sound like two people")

    # Whispered stretches against the normal-voice words of the same speaker.
    spans, cur = [], None
    for w in aligned:
        if w["quiet"]:
            if cur and cur["speaker"] == w["speaker"] and w["start"] - cur["end"] < 1.5:
                cur["end"] = w["end"]
            else:
                cur = {"speaker": w["speaker"], "start": w["start"], "end": w["end"]}
                spans.append(cur)
        else:
            cur = None
    report["whispers"] = []
    for s in spans:
        normal = [(w["start"], w["end"]) for w in aligned if not w["quiet"] and w["speaker"] == s["speaker"]]
        quiet_db, normal_db = rms_db(audio, [(s["start"], s["end"])]), rms_db(audio, normal)
        if quiet_db is None or normal_db is None:
            continue
        drop = round(normal_db - quiet_db, 1)
        report["whispers"].append({"start": s["start"], "end": s["end"], "drop_db": drop})
        if drop < 6:
            report["flags"].append(f"the whisper at {s['start']:.1f}s only drops {drop} dB; under 6 it barely reads as a whisper")
    return report


def expected_pitch(speaker_names=("FISH_VOICE_ID", "FISH_CLAUDE_VOICE_ID")):
    """{speaker index: normal pitch in Hz} from the *_PITCH_HZ values saved in .env."""
    expect = {}
    for i, name in enumerate(speaker_names):
        value = os.environ.get(name.replace("_ID", "_PITCH_HZ"), "")
        try:
            expect[i] = float(value)
        except ValueError:
            pass
    return expect


def show(report):
    print(report["scene"])
    for t in report["turns"]:
        hz = f"{t['pitch_hz']:6.1f} Hz" if t["pitch_hz"] else "    n/a   "
        off = f"  {t['off_pct']:+d}%" if "off_pct" in t else ""
        print(f"  speaker {t['speaker']}  {t['start']:6.2f}-{t['end']:6.2f}  {hz}{off}  {t['text']}")
    for w in report["whispers"]:
        print(f"  whisper {w['start']:6.2f}-{w['end']:6.2f}  drops {w['drop_db']} dB")
    for f in report["flags"]:
        print(f"  CHECK: {f}")
    if not report["flags"]:
        print("  nothing flagged")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("paths", nargs="+", help="scene folders (audio.wav + words.json), or audio files with --baseline")
    p.add_argument("--baseline", action="store_true", help="print the median pitch of plain audio files (your real voice)")
    p.add_argument("--expect", default="", help="normal pitch per speaker, e.g. 0=110,1=250 (default: the values in .env)")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    require_ffmpeg()
    load_env()

    if a.baseline:
        values = []
        for f in a.paths:
            hz = median_pitch(f)
            print(f"{f}: {hz} Hz")
            if hz:
                values.append(hz)
        if values:
            print(f"baseline: {statistics.median(values):.0f} Hz")
        return

    expect = expected_pitch()
    for pair in filter(None, a.expect.split(",")):
        k, v = pair.split("=")
        expect[int(k)] = float(v)
    reports = [check(path, expect=expect) for path in a.paths]
    if a.json:
        print(json.dumps(reports, indent=1))
    else:
        for r in reports:
            show(r)


if __name__ == "__main__":
    main()
