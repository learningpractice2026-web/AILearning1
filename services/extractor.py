"""Multi-step extraction pipeline (agent-style, single responsibility per step):
   Extractor (LLM -> JSON) -> Validator (Pydantic + 1 repair retry) -> Verifier (grounding + owner check)
Fully driven by usecase.yaml. Long inputs are map-reduced (extract per chunk, merge, de-duplicate)."""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher

from pydantic import ValidationError

from core import mock_engine, prompts
from core.config import get_settings
from core.guardrails import wrap_untrusted
from core.llm import get_llm
from core.logging_setup import get_logger
from core.schemas import Insights, Item
from core.usecase import UseCase, get_usecase

log = get_logger("extractor")


def _parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def _coerce(data: dict, uc: UseCase) -> Insights:
    """Accept small LLM shape deviations: sections at top level, summary under another name, etc."""
    if "sections" not in data:
        data["sections"] = {s.key: data.pop(s.key) for s in uc.sections if s.key in data}
    if "fields" not in data:
        data["fields"] = {f.name: data.pop(f.name) for f in uc.fields if f.name in data}
    data.setdefault("summary", data.pop("executive_summary", ""))
    ins = Insights.model_validate(data).normalise([s.key for s in uc.sections])
    for f in uc.fields:  # enforce option lists
        v = ins.fields.get(f.name, "")
        if f.options and v not in f.options:
            match = next((o for o in f.options if o.lower() == str(v).lower()), None)
            ins.fields[f.name] = match or (f.options[-1] if not v else str(v))
    return ins


def build_prompt(text: str, uc: UseCase) -> tuple[str, str, str]:
    system_t, user_t, version = prompts.load("extract")
    rules = "\n".join(f"{i}. {r}" for i, r in enumerate(uc.ai.rules, start=7))
    system = prompts.render(system_t, role=uc.ai.role, task=uc.ai.task, domain_rules=rules)
    user = prompts.render(user_t, speakers=", ".join(mock_engine.speakers(text)) or "none detected",
                          schema=uc.schema_hint(), input=wrap_untrusted(text))
    return system, user, version


def llm_extract(text: str, uc: UseCase, feedback: str = "") -> tuple[str, dict]:
    """One LLM extraction call. `feedback` = validation error from a previous attempt (repair loop)."""
    system, user, version = build_prompt(text, uc)
    if feedback:
        user += f"\n\nYour previous output was invalid: {feedback[:300]}. Return ONLY corrected JSON."
    res = get_llm().chat("extract", system, user, json_mode=True, use_cache=not feedback)
    return res.text, {"provider": res.provider, "model": res.model, "cached": res.cached,
                      "fallback_used": res.fallback_used, "prompt_version": version}


def parse(raw: str, uc: UseCase) -> Insights:
    """Validator: raises ValueError / ValidationError if the model output is unusable."""
    try:
        return _coerce(_parse_json(raw), uc)
    except (ValidationError, AttributeError, TypeError) as e:
        raise ValueError(str(e)) from e


def _extract_once(text: str, uc: UseCase) -> tuple[Insights, dict]:
    raw, meta = llm_extract(text, uc)
    meta["repaired"] = False
    try:
        return parse(raw, uc), meta
    except ValueError as e:
        log.info(f"Invalid JSON from model, one repair attempt: {e}")
        meta["repaired"] = True
        raw, _ = llm_extract(text, uc, feedback=str(e))
        try:
            return parse(raw, uc), meta
        except ValueError:
            meta["fallback_used"] = True
            return mock_engine.extract(text, uc), meta


def _split(text: str, max_chars: int) -> list[str]:
    """LangChain RecursiveCharacterTextSplitter: splits on speaker turns / paragraphs / sentences first,
    with overlap so an action item on a chunk boundary is not lost (duplicates are removed after merge)."""
    if len(text) <= max_chars:
        return [text]
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(chunk_size=max_chars, chunk_overlap=min(1500, max_chars // 10),
                                              separators=["\n\n", "\n", ". ", " ", ""])
    return splitter.split_text(text)


def _dedupe(items: list[Item]) -> list[Item]:
    out: list[Item] = []
    for it in items:
        if not any(SequenceMatcher(None, it.text.lower(), o.text.lower()).ratio() > 0.85 for o in out):
            out.append(it)
    return out


def verify(ins: Insights, text: str) -> tuple[Insights, dict]:
    """Verifier agent (deterministic, cheap, explainable): every item must be grounded in the input and
    every owner must exist in the input. Ungrounded items are kept but flagged for human review."""
    t_norm = " ".join(re.findall(r"[a-z0-9]+", text.lower()))
    padded = f" {t_norm} "
    names = {n.lower() for n in mock_engine.speakers(text)}
    flagged = total = 0
    for _, it in ins.all_items():
        total += 1
        ev = " ".join(re.findall(r"[a-z0-9]+", (it.evidence or it.text).lower()))
        if ev and ev in t_norm:
            it.grounded = True
        else:
            toks = ev.split()
            it.grounded = bool(toks) and sum(f" {w} " in padded for w in toks) / len(toks) >= 0.8
        if it.owner:
            first = it.owner.split()[0].lower()
            if first not in names and f" {first} " not in padded:
                it.owner = None  # hallucinated owner -> unassigned
                it.grounded = False
        if not it.grounded:
            it.confidence = min(it.confidence, 0.3)
            flagged += 1
    return ins, {"items_total": total, "items_flagged": flagged,
                 "grounding_rate": round(1 - flagged / total, 3) if total else 1.0}


def split(text: str) -> list[str]:
    return _split(text, get_settings().max_chars_per_call)


def map_reduce(parts: list[str], uc: UseCase) -> tuple[Insights, dict]:
    """Long inputs: extract each chunk, merge + de-duplicate, merge the summaries with one more LLM call."""
    from langchain_core.runnables import RunnableLambda
    # map step in parallel (LangChain batch with a concurrency cap to respect gateway rate limits)
    results = RunnableLambda(lambda p: _extract_once(p, uc)).batch(
        parts, config={"max_concurrency": get_settings().max_parallel})
    first, meta = results[0]
    ins = Insights(title=first.title, fields=first.fields, sections={s.key: [] for s in uc.sections})
    for r, _ in results:
        ins.highlights += r.highlights
        for k, items in r.sections.items():
            ins.items(k).extend(items)
    ins.sections = {k: _dedupe(v) for k, v in ins.sections.items()}
    sys_p, user_t, _ = prompts.load("summarize")
    ins.summary = get_llm().chat("summarize", sys_p,
                                 prompts.render(user_t, parts="\n\n".join(r.summary for r, _ in results))).text
    meta["chunks"] = len(parts)
    return ins, meta


def extract_insights(text: str, uc: UseCase | None = None) -> tuple[Insights, dict]:
    """Linear (non-graph) version of the same flow; the LangGraph version lives in services/graph.py."""
    uc = uc or get_usecase()
    parts = split(text)
    ins, meta = _extract_once(text, uc) if len(parts) == 1 else map_reduce(parts, uc)
    ins, vmeta = verify(ins, text)
    meta.update(vmeta)
    return ins, meta
