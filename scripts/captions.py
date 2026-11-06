#!/usr/bin/env python3
"""Turn words.json into captions.srt (short lines, broken at punctuation).

    python3 scripts/captions.py outputs/my-video/01-hook
"""
import json
import re
import sys
from pathlib import Path

MAX_WORDS, MAX_SEC = 6, 2.6
PAUSE = 0.3  # a gap this long ends the line (Fish Audio's timestamps carry no punctuation)


def ts(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def caption_lines(words, offset=0.0):
    """[(start, end, text)] with tags stripped, about one breath per line."""
    lines, cur = [], []
    for w in words:
        t = re.sub(r"<\|[^|]*\|>|<[^>]*>|\[[^\]]*\]", "", w["text"]).strip()
        if not t:
            continue
        if cur and w["start"] - cur[-1]["end"] >= PAUSE:
            lines.append(cur)
            cur = []
        cur.append({**w, "text": t})
        if len(cur) >= MAX_WORDS or cur[-1]["end"] - cur[0]["start"] >= MAX_SEC or t[-1] in ".?!,":
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    return [(ln[0]["start"] + offset, ln[-1]["end"] + offset, " ".join(w["text"] for w in ln)) for ln in lines]


def to_srt(lines):
    return "\n".join(f"{i}\n{ts(a)} --> {ts(b)}\n{text}\n" for i, (a, b, text) in enumerate(lines, 1))


def main():
    out_dir = Path(sys.argv[1])
    lines = caption_lines(json.loads((out_dir / "words.json").read_text()))
    (out_dir / "captions.srt").write_text(to_srt(lines))
    print(f"{len(lines)} caption lines -> {out_dir / 'captions.srt'}")


if __name__ == "__main__":
    main()
