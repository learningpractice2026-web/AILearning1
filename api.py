"""API-first: the same pipeline exposed as REST so Teams bots, Jira automations or an Angular UI can reuse it.
Run:  uvicorn api:app --reload --port 8000      Docs: http://localhost:8000/docs"""
from __future__ import annotations

import os

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from core import db
from core.config import get_settings
from core.usecase import get_usecase
from services import rag
from services.pipeline import process_text

app = FastAPI(title=f"{get_usecase().app.name} API", version="1.0")
db.init_db()


def _auth(x_api_key: str | None) -> None:
    """Set INBOUND_API_KEY to protect the API (callers send header X-API-Key). Unset = open (local dev)."""
    expected = os.getenv("INBOUND_API_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(401, "Invalid API key")


class RecordIn(BaseModel):
    text: str = Field(..., min_length=20, max_length=500_000)
    title: str = ""
    record_date: str = ""
    mask_pii: bool = True


class AskIn(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    record_ids: list[int] | None = None


@app.get("/health")
def health():
    return {"status": "ok", "usecase": get_usecase().slug, "llm_provider": get_settings().llm_provider}


@app.post("/records")
def create_record(body: RecordIn, x_api_key: str | None = Header(None)):
    _auth(x_api_key)
    rep = process_text(body.text, body.title, body.record_date, "api", body.mask_pii, "api")
    return {"record_id": rep.record_id, "insights": rep.insights.model_dump(), "meta": rep.meta,
            "pii_masked": rep.pii_counts, "injection_flags": rep.injection_hits}


@app.get("/records")
def list_records(q: str = "", x_api_key: str | None = Header(None)):
    _auth(x_api_key)
    return [{k: v for k, v in m.items() if k != "insights_json"} for m in db.list_records(q)]


@app.get("/records/{mid}")
def get_record(mid: int, x_api_key: str | None = Header(None)):
    _auth(x_api_key)
    m = db.get_record(mid)
    if not m:
        raise HTTPException(404, "Not found")
    return {"id": m["id"], "title": m["title"], "insights": m["insights"].model_dump(), "approved": bool(m["approved"])}


@app.post("/ask")
def ask(body: AskIn, x_api_key: str | None = Header(None)):
    _auth(x_api_key)
    a = rag.ask(body.question, body.record_ids)
    return {"answer": a.text, "refused": a.refused,
            "citations": [{"cite": h.cite, "record": h.title, "score": round(h.score, 3)} for h in a.hits]}
