"""Single entry point used by the UI, API and eval.
USE_LANGGRAPH=true  -> runs the LangGraph state graph (services/graph.py)
USE_LANGGRAPH=false -> same steps as plain Python (fallback if langgraph is not installed)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from core import db
from core.config import get_settings
from core.guardrails import check_input_size, detect_injection, guard_output, mask_pii
from core.logging_setup import get_logger
from core.schemas import Insights
from core.usecase import get_usecase
from services import cleaner, extractor, rag

log = get_logger("pipeline")


@dataclass
class PipelineReport:
    record_id: int | None = None
    insights: Insights | None = None
    pii_counts: dict = field(default_factory=dict)
    injection_hits: list[str] = field(default_factory=list)
    guard_events: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    trace: list[str] = field(default_factory=list)
    engine: str = "python"
    seconds: float = 0.0


def _langgraph_available() -> bool:
    import importlib.util
    return importlib.util.find_spec("langgraph") is not None


def process_text(raw_text: str, title: str = "", record_date: str = "", source_name: str = "pasted",
                 mask: bool = True, user: str = "system", store: bool = True,
                 on_step: Callable[[str], None] | None = None) -> PipelineReport:
    if get_settings().use_langgraph and _langgraph_available():
        from services import graph
        state, secs = graph.run(raw=raw_text, title=title, record_date=record_date, source_name=source_name,
                                mask=mask, user=user, store=store, on_step=on_step)
        return PipelineReport(state.get("record_id"), state["insights"], state.get("pii_counts", {}),
                              state.get("injection_hits", []), state.get("events", []), state.get("meta", {}),
                              state.get("trace", []), "langgraph", secs)
    return _process_plain(raw_text, title, record_date, source_name, mask, user, store, on_step)


def _process_plain(raw_text, title, record_date, source_name, mask, user, store, on_step) -> PipelineReport:
    t0 = time.perf_counter()
    step = on_step or (lambda _m: None)
    rep = PipelineReport(engine="python")
    uc = get_usecase()
    step("🧹 Cleaning input")
    text = cleaner.clean_text(raw_text)
    if not text.strip():
        raise ValueError("Input is empty after cleaning.")
    if err := check_input_size(text, uc.guardrails.max_input_chars):
        raise ValueError(err)
    step("🛡️ Input guardrails")
    if mask:
        text, rep.pii_counts = mask_pii(text)
    rep.injection_hits = detect_injection(text)
    step("🧠 Extract + validate + verify")
    ins, meta = extractor.extract_insights(text, uc)
    if title:
        ins.title = title
    step("🛡️ Output guardrails")
    rep.guard_events = guard_output(ins, mask, uc.guardrails.blocked_terms)
    rep.insights, rep.meta = ins, meta
    rep.trace = ["clean", "guard_input", "extract", "validate", "verify", "guard_output"]
    if store:
        step("💾 Saving + indexing")
        flags = [f"injection: {h}" for h in rep.injection_hits] + rep.guard_events
        if rep.pii_counts:
            flags.append(f"pii_masked: {rep.pii_counts}")
        rep.record_id = db.save_record(ins.title, record_date, source_name, text, ins, bool(rep.pii_counts),
                                       flags, user)
        rag.index_record(rep.record_id, text)
        rep.trace.append("store")
    rep.seconds = round(time.perf_counter() - t0, 2)
    return rep
