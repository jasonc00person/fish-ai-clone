"""Line the script up with Fish Audio's word timestamps.

The timestamps carry bare words: no punctuation, no tags, no speakers. The script
has all of that. Matching the two tells every timed word who said it, which
direction it was under, and whether a sentence ends there. Standard library only.
"""
import difflib
import re

TOKEN = re.compile(r"<\|speaker:(\d+)\|>|<\|[^|]*\|>|\[([^\]]*)\]|<(/?)([a-zA-Z_]+)>|(\n\s*\n)|([^\s\[\]<>]+)")
QUIET = ("whisper", "hushed", "under his breath", "under her breath", "barely audible", "mutter", "murmur")


def norm(word):
    return re.sub(r"[^\w']", "", word.lower()).strip("'")


def script_tokens(text):
    """Every spoken word in the script, in order, with its speaker and delivery."""
    tokens, speaker, direction, open_tags = [], 0, "", []
    for m in TOKEN.finditer(text):
        spk, bracket, closing, tag, para, word = m.groups()
        if spk is not None:
            speaker, direction = int(spk), ""
        elif bracket is not None:
            direction = bracket.lower()
        elif tag:
            tag = tag.lower()
            if closing:
                if tag in open_tags:
                    open_tags.remove(tag)
            else:
                open_tags.append(tag)
        elif para:
            if tokens:
                tokens[-1]["sentence_end"] = True
        elif word and norm(word):
            tokens.append({
                "raw": word, "norm": norm(word), "speaker": speaker, "direction": direction,
                "quiet": any(q in direction for q in QUIET) or "whisper" in open_tags,
                "sentence_end": word.rstrip("\"')”’")[-1:] in ".?!",
            })
    if tokens:
        tokens[-1]["sentence_end"] = True
    return tokens


def align(text, words):
    """Copy of words.json where each entry also has speaker, direction, quiet, sentence_end and raw
    (the word as written in the script, punctuation included, when it matched)."""
    expected = script_tokens(text)
    timed = [w for w in words if norm(re.sub(r"<\|[^|]*\|>|<[^>]*>|\[[^\]]*\]", "", w["text"]))]
    got = [norm(re.sub(r"<\|[^|]*\|>|<[^>]*>|\[[^\]]*\]", "", w["text"])) for w in timed]
    out = [dict(w) for w in timed]
    if not expected:
        for w in out:
            w.update(speaker=0, direction="", quiet=False, sentence_end=False, raw=w["text"].strip())
        return out

    matcher = difflib.SequenceMatcher(None, [t["norm"] for t in expected], got, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        for k, j in enumerate(range(j1, j2)):
            if op == "equal":
                src, matched = expected[i1 + k], True
            else:
                # A word the model changed, added or split: borrow from the nearest script word.
                src = expected[min(i1 + k, max(i2 - 1, i1), len(expected) - 1)]
                matched = False
            out[j].update(speaker=src["speaker"], direction=src["direction"], quiet=src["quiet"],
                          sentence_end=src["sentence_end"] if matched or j == j2 - 1 else False,
                          raw=src["raw"] if matched else out[j]["text"].strip())
    return out


def mismatches(text, words):
    """[(script words, audio words)] for every place the audio's words differ from the script's."""
    expected = [t["norm"] for t in script_tokens(text)]
    got = [n for n in (norm(re.sub(r"<\|[^|]*\|>|<[^>]*>|\[[^\]]*\]", "", w["text"])) for w in words) if n]
    ops = difflib.SequenceMatcher(None, expected, got, autojunk=False).get_opcodes()
    return [(" ".join(expected[i1:i2]), " ".join(got[j1:j2])) for op, i1, i2, j1, j2 in ops if op != "equal"]


def turns(aligned):
    """Group aligned words into speaker turns: [{speaker, start, end, text}]."""
    out = []
    for w in aligned:
        if out and out[-1]["speaker"] == w["speaker"]:
            out[-1]["end"] = w["end"]
            out[-1]["text"] += " " + w["raw"]
        else:
            out.append({"speaker": w["speaker"], "start": w["start"], "end": w["end"], "text": w["raw"]})
    return out
