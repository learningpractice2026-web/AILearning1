"""LangGraph orchestration of the pipeline — an explicit, inspectable agent workflow.

    clean → guard_input → extract ─(single chunk)→ validate ─ok→ verify → guard_output → store → END
                              │                     │  invalid & attempts<2 → extract (repair loop)
                              │                     └  invalid again        → fallback ─→ verify
                              └─(long input: map-reduce)──────────────────────────────→ verify

Each node has one responsibility (Extractor / Validator / Verifier / Guard agents). The graph is compiled once.
`mermaid()` returns the diagram for the Admin page and the D3 document."""
from __future__ import annotations

import time
from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from core import db, mock_engine
from core.guardrails import check_input_size, detect_injection, guard_output, mask_pii
from core.schemas import Insights
from core.usecase import get_usecase
from services import cleaner, extractor, rag

MAX_ATTEMPTS = 2


class PipelineState(TypedDict, total=False):
    raw: str
    title: str
    record_date: str
    source_name: str
    mask: bool
    user: str
    store: bool
    on_step: Callable[[str], None]
    text: str
    parts: list[str]
    pii_counts: dict
    injection_hits: list[str]
    llm_raw: str
    error: str
    attempts: int
    insights: Insights | None
    meta: dict
    events: list[str]
    trace: list[str]
    record_id: int | None


def _step(state: PipelineState, node: str, msg: str) -> list[str]:
    if cb := state.get("on_step"):
        cb(msg)
    return [*state.get("trace", []), node]


# ----------------------------------------------------------------- nodes
def clean(state: PipelineState) -> dict:
    trace = _step(state, "clean", "🧹 Cleaning input")
    text = cleaner.clean_text(state["raw"])
    if not text.strip():
        raise ValueError("Input is empty after cleaning.")
    if err := check_input_size(text, get_usecase().guardrails.max_input_chars):
        raise ValueError(err)
    return {"text": text, "trace": trace, "events": [], "attempts": 0, "meta": {}}


def guard_input(state: PipelineState) -> dict:
    trace = _step(state, "guard_input", "🛡️ Input guardrails: PII masking + prompt-injection scan")
    text, counts = mask_pii(state["text"]) if state.get("mask", True) else (state["text"], {})
    return {"text": text, "pii_counts": counts, "injection_hits": detect_injection(text),
            "parts": extractor.split(text), "trace": trace}


def extract(state: PipelineState) -> dict:
    uc = get_usecase()
    if len(state["parts"]) > 1:
        trace = _step(state, "extract", f"🧠 Long input: map-reduce over {len(state['parts'])} chunks")
        ins, meta = extractor.map_reduce(state["parts"], uc)
        return {"insights": ins, "meta": {**state["meta"], **meta}, "trace": trace}
    attempt = state.get("attempts", 0) + 1
    label = "🧠 Extractor agent: LLM → structured JSON" if attempt == 1 else "🔁 Repair loop: asking the LLM to fix its JSON"
    trace = _step(state, "extract", label)
    raw, meta = extractor.llm_extract(state["text"], uc, feedback=state.get("error", "") if attempt > 1 else "")
    return {"llm_raw": raw, "attempts": attempt, "meta": {**state["meta"], **meta, "repaired": attempt > 1},
            "trace": trace}


def validate(state: PipelineState) -> dict:
    trace = _step(state, "validate", "✅ Validator: schema check (Pydantic)")
    try:
        return {"insights": extractor.parse(state["llm_raw"], get_usecase()), "error": "", "trace": trace}
    except ValueError as e:
        return {"insights": None, "error": str(e), "trace": trace}


def fallback(state: PipelineState) -> dict:
    trace = _step(state, "fallback", "🛟 Fallback: offline rules engine")
    return {"insights": mock_engine.extract(state["text"], get_usecase()),
            "meta": {**state["meta"], "fallback_used": True}, "trace": trace}


def verify(state: PipelineState) -> dict:
    trace = _step(state, "verify", "🔎 Verifier agent: grounding every item in the source")
    ins, vmeta = extractor.verify(state["insights"], state["text"])
    if state.get("title"):
        ins.title = state["title"]
    return {"insights": ins, "meta": {**state["meta"], **vmeta}, "trace": trace}


def guard_out(state: PipelineState) -> dict:
    trace = _step(state, "guard_output", "🛡️ Output guardrails: PII leak + blocked terms + reliability")
    ins = state["insights"]
    events = guard_output(ins, state.get("mask", True), get_usecase().guardrails.blocked_terms)
    return {"insights": ins, "events": [*state.get("events", []), *events], "trace": trace}


def store(state: PipelineState) -> dict:
    trace = _step(state, "store", "💾 Saving + building the RAG index")
    ins = state["insights"]
    flags = [f"injection: {h}" for h in state.get("injection_hits", [])]
    if state.get("pii_counts"):
        flags.append(f"pii_masked: {state['pii_counts']}")
    flags += state.get("events", [])
    rid = db.save_record(ins.title, state.get("record_date", ""), state.get("source_name", ""), state["text"], ins,
                         bool(state.get("pii_counts")), flags, state.get("user", "system"))
    rag.index_record(rid, state["text"])
    return {"record_id": rid, "trace": trace}


# ----------------------------------------------------------------- routing
def after_extract(state: PipelineState) -> str:
    return "verify" if state.get("insights") is not None and len(state["parts"]) > 1 else "validate"


def after_validate(state: PipelineState) -> str:
    if state.get("insights") is not None:
        return "verify"
    return "extract" if state.get("attempts", 0) < MAX_ATTEMPTS else "fallback"


def after_guard(state: PipelineState) -> str:
    return "store" if state.get("store", True) else END


def build_graph():
    g = StateGraph(PipelineState)
    for name, fn in [("clean", clean), ("guard_input", guard_input), ("extract", extract), ("validate", validate),
                     ("fallback", fallback), ("verify", verify), ("guard_output", guard_out), ("store", store)]:
        g.add_node(name, fn)
    g.add_edge(START, "clean")
    g.add_edge("clean", "guard_input")
    g.add_edge("guard_input", "extract")
    g.add_conditional_edges("extract", after_extract, {"validate": "validate", "verify": "verify"})
    g.add_conditional_edges("validate", after_validate,
                            {"verify": "verify", "extract": "extract", "fallback": "fallback"})
    g.add_edge("fallback", "verify")
    g.add_edge("verify", "guard_output")
    g.add_conditional_edges("guard_output", after_guard, {"store": "store", END: END})
    g.add_edge("store", END)
    return g.compile()


_GRAPH = None


def get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def mermaid() -> str:
    return get_graph().get_graph().draw_mermaid()


def run(**inputs: Any) -> tuple[PipelineState, float]:
    t0 = time.perf_counter()
    state = get_graph().invoke(inputs)
    return state, round(time.perf_counter() - t0, 2)
