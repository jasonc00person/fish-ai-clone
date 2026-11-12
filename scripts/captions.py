#!/usr/bin/env python3
"""Turn words.json into captions.srt (short lines, one breath each).

    python3 scripts/captions.py outputs/my-video/01-hook

Fish Audio's timestamps carry bare words, so the punctuation and capitals come
from the script (scene.txt in the same folder) and the line breaks come from
sentence ends and pauses.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from align import align  # noqa: E402

MAX_WORDS, MAX_SEC = 6, 2.6
PAUSE = 0.3  # a gap this long ends the line


def ts(t):
    ms = int(round(max(t, 0) * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def caption_lines(words, offset=0.0, text=None):
    """[(start, end, text)] with tags stripped, about one breath per line."""
    if text:
        words = [{**w, "text": w["raw"]} for w in align(text, words)]
    lines, cur = [], []
    for w in words:
        t = re.sub(r"<\|[^|]*\|>|<[^>]*>|\[[^\]]*\]", "", w["text"]).strip()
        if not t:
            continue
        if cur and (w["start"] - cur[-1]["end"] >= PAUSE or w.get("speaker") != cur[-1].get("speaker")):
            lines.append(cur)
            cur = []
        cur.append({**w, "text": t})
        if len(cur) >= MAX_WORDS or cur[-1]["end"] - cur[0]["start"] >= MAX_SEC or t[-1] in ".?!":
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    out = []
    for i, ln in enumerate(lines):
        start, end = ln[0]["start"], max(ln[-1]["end"], ln[0]["start"] + 0.3)
        if i + 1 < len(lines):
            end = min(end, lines[i + 1][0]["start"])
        out.append((start + offset, end + offset, " ".join(w["text"] for w in ln)))
    return out


def scene_text(scene_dir):
    f = Path(scene_dir) / "scene.txt"
    return f.read_text() if f.is_file() else None


def to_srt(lines):
    return "\n".join(f"{i}\n{ts(a)} --> {ts(b)}\n{text}\n" for i, (a, b, text) in enumerate(lines, 1))


def main():
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        sys.exit(__doc__)
    out_dir = Path(sys.argv[1])
    lines = caption_lines(json.loads((out_dir / "words.json").read_text()), text=scene_text(out_dir))
    (out_dir / "captions.srt").write_text(to_srt(lines))
    print(f"{len(lines)} caption lines -> {out_dir / 'captions.srt'}")


if __name__ == "__main__":
    main()
