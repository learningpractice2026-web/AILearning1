"""Input cleaning: fillers, stutters, timestamps, speaker-label normalisation (safe for non-dialogue text too)."""
from __future__ import annotations

import re

FILLERS = re.compile(r"(?<![\w-])(?:um+|uh+|erm+|hmm+|ah+|you know|i mean|sort of|kind of)(?![\w-])[,.]?\s*",
                     re.IGNORECASE)
TIMESTAMP = re.compile(r"^\s*\[?\(?\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?\]?\)?\s*[-–]?\s*")
SPEAKER_N = re.compile(r"^\s*(?:speaker|spk)[\s_-]*(\d+)\s*[:\-]\s*", re.IGNORECASE)
NAME_DASH = re.compile(r"^\s*([A-Z][\w.'-]+(?: [A-Z][\w.'-]+)?)\s+[-–]\s+")
REPEAT_WORD = re.compile(r"\b(\w+)(\s+\1\b)+", re.IGNORECASE)


def clean_text(text: str) -> str:
    lines = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = TIMESTAMP.sub("", raw)
        line = SPEAKER_N.sub(lambda m: f"Speaker {m.group(1)}: ", line)
        line = NAME_DASH.sub(lambda m: f"{m.group(1)}: ", line)
        line = FILLERS.sub("", line)
        line = REPEAT_WORD.sub(r"\1", line)
        line = re.sub(r"\s+([,.?!])", r"\1", line)
        line = re.sub(r",\s*,", ",", line)
        line = re.sub(r":\s*,\s*", ": ", line)
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def stats(raw: str, cleaned: str) -> dict:
    return {"raw_chars": len(raw), "clean_chars": len(cleaned),
            "reduction_pct": round(100 * (1 - len(cleaned) / max(len(raw), 1)), 1),
            "lines": cleaned.count("\n") + 1 if cleaned else 0}
