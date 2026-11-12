"""Input/output guardrails: PII masking, prompt-injection detection, output sanity.
Deterministic and offline on purpose - they must work even when the LLM is down.
Production upgrade path: Azure AI Content Safety / Presidio / Prompt Shields."""
from __future__ import annotations

import re

PII_PATTERNS: dict[str, re.Pattern] = {
    "EMAIL": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "PHONE": re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)"),
    "AADHAAR": re.compile(r"(?<!\d)\d{4}\s\d{4}\s\d{4}(?!\d)"),
    "PAN": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    "CARD": re.compile(r"(?<!\d)(?:\d[ -]?){13,16}(?!\d)"),
    "IP": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}

INJECTION_PATTERNS = [
    r"ignore (all |any )?(the )?(previous|prior|above) (instructions|prompts?)",
    r"disregard (all |the )?(previous|prior|above|system)",
    r"you are now\b",
    r"\bsystem prompt\b",
    r"reveal (your|the) (prompt|instructions)",
    r"\bjailbreak\b",
    r"\bDAN mode\b",
    r"act as (an? )?(unrestricted|unfiltered)",
    r"mark all .* as (completed|done|closed)",
]
_INJ = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def mask_pii(text: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    for label, pat in PII_PATTERNS.items():
        text, n = pat.subn(f"[{label}]", text)
        if n:
            counts[label] = n
    return text, counts


def detect_injection(text: str) -> list[str]:
    hits = []
    for line in text.splitlines():
        if any(p.search(line) for p in _INJ):
            hits.append(line.strip()[:200])
    return hits


def wrap_untrusted(text: str) -> str:
    """Spotlighting: mark user content as data so the model does not execute it."""
    return f"<<<INPUT_START>>>\n{text}\n<<<INPUT_END>>>"


def check_question(question: str) -> str | None:
    """Returns a refusal reason, or None if the question is OK."""
    if len(question) > 2000:
        return "Question too long (max 2000 characters)."
    if detect_injection(question):
        return "This looks like a prompt-injection attempt, so I won't run it. Please ask about the stored content."
    return None


# ------------------------------------------------------------------ output guardrails
DEFAULT_BLOCKED = ["kill yourself", "racial slur", "bomb making", "credit card dump"]


def check_input_size(text: str, max_chars: int) -> str | None:
    if len(text) > max_chars:
        return f"Input too large ({len(text):,} chars, limit {max_chars:,}). Split it into smaller parts."
    return None


def guard_output(ins, mask: bool, blocked_terms: list[str]) -> list[str]:
    """Runs on the AI OUTPUT before anyone sees it:
    1) PII leak check — re-masks any PII the model produced (e.g. reconstructed from context);
    2) blocked/unsafe terms — items are flagged (not silently dropped) for human review;
    3) unverified-item ratio — warns when the model looks unreliable for this input."""
    events: list[str] = []
    terms = [t.lower() for t in (blocked_terms or []) + DEFAULT_BLOCKED]

    def clean(s: str) -> str:
        if not s:
            return s
        if mask:
            s2, counts = mask_pii(s)
            if counts:
                events.append(f"output PII re-masked: {counts}")
            s = s2
        return s

    ins.summary = clean(ins.summary)
    ins.highlights = [clean(h) for h in ins.highlights]
    total = flagged = 0
    for _, it in ins.all_items():
        total += 1
        it.text, it.evidence = clean(it.text), clean(it.evidence)
        it.owner = clean(it.owner) if it.owner else it.owner
        hit = next((t for t in terms if t in it.text.lower()), None)
        if hit:
            it.grounded = False
            events.append(f"blocked term '{hit}' in output item -> flagged for review")
        flagged += not it.grounded
    if total and flagged / total > 0.5:
        events.append(f"{flagged}/{total} items unverified -> low reliability, human review required")
    return events
