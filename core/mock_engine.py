"""Offline rules engine driven by usecase.yaml keywords.
Used (1) when LLM_PROVIDER=mock, (2) as FALLBACK when the provider fails / budget is exhausted.
Keeps the live demo alive without Wi-Fi, and doubles as the 'traditional baseline' in the eval (D4)."""
from __future__ import annotations

import json
import re
from collections import Counter

from core.schemas import Insights, Item
from core.usecase import UseCase, get_usecase

DAYS = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
DEADLINE_RE = re.compile(
    rf"\b(?:by|before|until|on|within)?\s*((?:next\s+)?{DAYS}|tomorrow|today|tonight|eod|end of (?:the )?(?:day|week|sprint|month)"
    rf"|next week|\d{{1,2}}(?::\d{{2}})?\s?(?:am|pm)|\d+\s+(?:minutes?|mins?|hours?|hrs?|days?|business days)"
    rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*)\b",
    re.IGNORECASE)
SELF_RE = re.compile(r"\b(i'll|i will|i can take|i am going to|i'm going to|i shall)\b", re.IGNORECASE)
ASK_RE = re.compile(r"^\s*([A-Z][a-z]+),?\s+(?:can|could|will|would) you\b")
NAMED_RE = re.compile(r"\b([A-Z][a-z]+)(?: from (?:the )?[\w -]{2,30}?)? (?:will|to own|owns|is going to)\b")
PARTY_RE = re.compile(r"\b(?:[Tt]he\s+)?([A-Z][a-zA-Z]+)(?:'s)?\s+(?:shall|must|agrees to|is required to|will provide)\b")
NOT_NAMES = {"we", "they", "it", "this", "that", "team", "someone", "somebody", "everyone", "who", "which", "there",
             "the", "he", "she", "you", "i", "please", "also", "then"}
HEADER_KEYS = {"meeting", "date", "participants", "agenda", "title", "subject", "from", "to", "ticket", "id"}
STOP = set("the a an and or to of in on for is are was were be we i you it that this with at by from as our can "
           "will just so but not have has do does need yes okay ok also let's lets".split())


SPEAKER_RE = re.compile(r"^\s*([A-Z][a-zA-Z.'-]+(?: [A-Z][a-zA-Z.'-]+){0,2})\s*:\s*(.+)$")


def _utterances(text: str) -> list[tuple[str | None, str]]:
    """Dialogue lines 'Name: text' -> (Name, text); other lines -> (None, line)."""
    out = []
    for line in text.splitlines():
        m = SPEAKER_RE.match(line)
        if m and m.group(1).lower() not in HEADER_KEYS:
            out.append((m.group(1).strip(), m.group(2).strip()))
        elif line.strip() and not (m and m.group(1).lower() in HEADER_KEYS):
            out.append((None, line.strip()))
    return out


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def speakers(text: str) -> list[str]:
    return sorted({s for s, _ in _utterances(text) if s})


def _deadline(s: str) -> str | None:
    m = DEADLINE_RE.search(s)
    return m.group(1).strip() if m else None


def _header(text: str, key: str) -> str | None:
    m = re.search(rf"^\s*{key}\s*:\s*(.+)$", "\n".join(text.splitlines()[:6]), re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else None


def extract(text: str, uc: UseCase | None = None) -> Insights:
    uc = uc or get_usecase()
    utts = _utterances(text)
    names = {s for s, _ in utts if s}
    out = Insights(sections={s.key: [] for s in uc.sections})
    order = [(s, s.keyword_regex()) for s in uc.priority()]
    highlights = []

    for speaker, line in utts:
        for sent in _sentences(line):
            if len(sent.split()) < uc.offline.min_words:
                continue
            for sec, rx in order:
                if rx is None or not rx.search(sent):
                    continue
                owner = None
                if sec.has_owner:
                    if sec.is_task:
                        m_ask, m_named = ASK_RE.search(sent), NAMED_RE.search(sent)
                        if SELF_RE.search(sent):
                            owner = speaker
                        elif m_ask and m_ask.group(1) in names:
                            owner = m_ask.group(1)
                        elif m_named and (m_named.group(1) in names or
                                          (not uc.app.dialogue and m_named.group(1).lower() not in NOT_NAMES)):
                            owner = m_named.group(1)
                        elif not uc.app.dialogue and (m_party := PARTY_RE.search(sent)) \
                                and m_party.group(1).lower() not in NOT_NAMES:
                            owner = m_party.group(1)
                    else:
                        owner = speaker
                attrs = {}
                for a in sec.attributes:  # pick the first option literally mentioned, else leave blank
                    hit = next((o for o in a.options if re.search(rf"\b{re.escape(o)}\b", sent, re.I)), None)
                    if hit:
                        attrs[a.name] = hit
                out.sections[sec.key].append(Item(
                    text=sent, owner=owner, deadline=_deadline(sent) if sec.has_deadline else None,
                    evidence=sent, confidence=0.55, attributes=attrs))
                break
            else:
                if len(sent.split()) >= 9 and len(highlights) < 6:
                    highlights.append(f"{speaker}: {sent}" if speaker else sent)

    out.title = _header(text, "title") or _header(text, "meeting") or _header(text, "subject") \
        or f"{uc.app.record_name} {', '.join(sorted(names)[:3])}".strip()
    for f in uc.fields:  # option with most keyword hits (YAML keywords, else the option's own first word)
        if f.options:
            scores = {o: sum(len(re.findall(rx, text, re.I))
                             for rx in (f.keywords.get(o) or [rf"\b{re.escape(o.split()[0])}"])) for o in f.options}
            best = max(scores, key=scores.get)
            neutral = next((o for o in f.options if o.lower() in {"neutral", "general", "other", "unknown", "medium"}),
                           f.options[-1])
            out.fields[f.name] = best if scores[best] else neutral
    lower_names = {n.lower() for n in names}
    words = [w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{3,}", text.lower())
             if w not in STOP and w not in lower_names and w not in HEADER_KEYS]
    topics = ", ".join(w for w, _ in Counter(words).most_common(6))
    counts = ", ".join(f"{len(out.sections[s.key])} {s.label.lower()}" for s in uc.sections)
    who = f" with {len(names)} participants ({', '.join(sorted(names))})" if names else ""
    out.summary = f"{uc.app.record_name}{who}. Main topics: {topics}. Extracted: {counts}. (offline rules engine)"
    out.highlights = highlights
    return out


def answer(question: str, blocks: list[tuple[str, str]]) -> str:
    q = {w for w in re.findall(r"[a-z0-9]+", question.lower()) if w not in STOP and len(w) > 2}
    scored = []
    for cite, text in blocks:
        for s in _sentences(text.replace("\n", " ")):
            overlap = len(q & set(re.findall(r"[a-z0-9]+", s.lower())))
            if overlap:
                scored.append((overlap, s, cite))
    if not scored:
        return "I couldn't find that information in the records."
    scored.sort(key=lambda x: -x[0])
    return "From the records (offline mode):\n" + "\n".join(f"- {s} [{c}]" for _, s, c in scored[:3])


def respond(task: str, user_prompt: str) -> str:
    """Mock 'LLM' entry point used by the gateway."""
    if task == "extract":
        m = re.search(r"<<<INPUT_START>>>\n(.*)\n<<<INPUT_END>>>", user_prompt, re.S)
        return extract(m.group(1) if m else user_prompt).model_dump_json()
    if task == "answer":
        q = re.search(r"QUESTION:\s*(.+)", user_prompt)
        blocks = re.findall(r"\[(R\d+#\d+)\]\n(.*?)(?=\n\[R\d+#\d+\]\n|\Z)", user_prompt, re.S)
        return answer(q.group(1) if q else "", blocks)
    if task == "summarize":
        return user_prompt.split("\n\n")[-1][:1200]
    return json.dumps({"note": "mock response", "task": task})
