"""Exercises the REAL LangChain code path against a tiny fake OpenAI-compatible server (no key / internet):
router, LangChain SQLite cache, JSON repair loop in the LangGraph pipeline, fallback, vision/scanned-PDF OCR,
large-document map-reduce."""
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from core import db
from core import llm as llm_mod
from core.config import get_settings
from core.llm import LLMGateway
from core.usecase import get_usecase

GOOD = {"title": "Fake", "summary": "ok", "fields": {"category": "Standup"}, "sections": {"action_items": [
    {"text": "Fix login", "owner": "Rahul", "deadline": "Friday", "evidence": "I'll fix login", "confidence": 0.9}]}}


class Fake(BaseHTTPRequestHandler):
    queue: list = []      # scripted replies (str content) or int (HTTP error status)
    calls: list = []

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.calls.append(body)
        reply = Fake.queue.pop(0) if Fake.queue else json.dumps(GOOD)
        if isinstance(reply, int):
            self.send_response(reply)
            self.end_headers()
            return
        data = json.dumps({"id": "x", "object": "chat.completion", "created": 0, "model": body.get("model", "m"),
                           "choices": [{"index": 0, "finish_reason": "stop",
                                        "message": {"role": "assistant", "content": reply}}],
                           "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.fixture()
def gateway(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    Fake.queue, Fake.calls = [], []
    s = get_settings()
    g = LLMGateway(s.__class__(**{**s.__dict__, "llm_provider": "openai", "api_key": "x",
                                  "base_url": f"http://127.0.0.1:{srv.server_port}/v1",
                                  "router_threshold_chars": 50}))
    monkeypatch.setattr("time.sleep", lambda *_: None)
    monkeypatch.setattr(llm_mod, "_gateway", g)
    yield g
    srv.shutdown()


def test_router_cache_and_fallback(gateway):
    r1 = gateway.chat("extract", "sys", "x" * 100, json_mode=True)
    assert r1.provider == "openai" and r1.model == gateway.s.model_strong      # long -> strong model
    assert Fake.calls[0]["response_format"] == {"type": "json_object"}
    r2 = gateway.chat("extract", "sys", "x" * 100, json_mode=True)
    assert r2.cached and len(Fake.calls) == 1                                    # LangChain SQLite cache hit
    assert gateway.chat("answer", "sys", "short").model == gateway.s.model_fast  # router -> cheap model
    Fake.queue = [500, 500, 500, 500]
    r3 = gateway.chat("answer", "sys", "QUESTION: who?\n\nCONTEXT:\n[R1#0]\nRahul: I'll fix login", use_cache=False)
    assert r3.fallback_used and r3.provider == "mock"                           # graceful degradation
    calls = db.llm_calls()
    assert any(c["status"] == "error" for c in calls) and any(c["cost_usd"] > 0 for c in calls)


def test_langgraph_repair_loop(gateway):
    from services.pipeline import process_text
    Fake.queue = ["this is not json", json.dumps(GOOD)]
    rep = process_text("Rahul: I'll fix login by Friday.", store=False)
    assert rep.engine == "langgraph"
    assert rep.trace.count("extract") == 2 and "fallback" not in rep.trace     # repaired on 2nd attempt
    assert rep.meta["repaired"] and rep.insights.sections["action_items"][0].owner == "Rahul"
    Fake.queue = ["bad", "still bad"]
    rep = process_text("Priya: I will deploy on Monday.", store=False)
    assert "fallback" in rep.trace and rep.meta["fallback_used"]                 # gives up -> rules engine


def test_scanned_pdf_and_image_go_to_vision_model(gateway):
    from PIL import Image

    from services import ingest
    Fake.queue = ["Rahul: I'll fix the login API by Friday."]
    buf = io.BytesIO()
    Image.new("RGB", (400, 200), "white").save(buf, format="PDF")              # image-only (scanned) PDF
    text, meta = ingest.read_upload_with_meta("scan.pdf", buf.getvalue())
    assert "login API" in text and meta["modality"] == "pdf + vision OCR"
    sent = Fake.calls[-1]["messages"][0]["content"]
    assert any(p.get("type") == "image_url" for p in sent)                      # multimodal message
    Fake.queue = ["Whiteboard: Decision - use JWT"]
    img = io.BytesIO()
    Image.new("RGB", (50, 50)).save(img, format="PNG")
    assert "JWT" in ingest.read_upload("board.png", img.getvalue())


def test_large_document_map_reduce(monkeypatch):
    """Mock provider; tiny chunk size forces LangChain splitter + parallel map-reduce inside the graph."""
    from services import extractor
    from services.pipeline import process_text
    s = get_settings()
    monkeypatch.setattr(extractor, "get_settings", lambda: s.__class__(**{**s.__dict__, "max_chars_per_call": 400}))
    raw = (get_usecase().samples_dir / "sprint_planning.txt").read_text(encoding="utf-8")
    rep = process_text(raw, store=False)
    assert rep.meta["chunks"] > 1 and "validate" not in rep.trace               # map-reduce branch
    owners = {a.owner for a in rep.insights.sections["action_items"]}
    assert {"Rahul", "Priya", "Vikram", "Meera"} <= owners                     # nothing lost at chunk borders
    texts = [a.text for a in rep.insights.sections["action_items"]]
    assert len(texts) == len(set(texts))                                         # overlap duplicates removed


def test_output_guardrails():
    from core.guardrails import guard_output
    from core.schemas import Insights, Item
    ins = Insights(summary="Contact a@b.com", sections={"risks": [Item(text="how to do bomb making", evidence="x")]})
    events = guard_output(ins, mask=True, blocked_terms=[])
    assert "[EMAIL]" in ins.summary and not ins.sections["risks"][0].grounded
    assert any("blocked term" in e for e in events) and any("PII" in e for e in events)
