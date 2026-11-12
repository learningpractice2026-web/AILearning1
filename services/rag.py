"""RAG over all stored records — LangChain components:
- Chunking:  RecursiveCharacterTextSplitter (keeps speaker turns / paragraphs together, with overlap)
- Retriever: HybridRetriever (LangChain BaseRetriever) = BM25 keyword score + embedding cosine (if EMBED_MODEL set).
             Hybrid matters: IDs and names (JWT, CHG-4471, Rahul) match better on keywords; meaning on vectors.
             BM25-only still works offline / without an embedding model.
- Chain:     LCEL  retriever -> format with citations -> LLM (through the gateway: router, cache, budget, fallback)
Answers cite [R<record>#<chunk>] and say "not found" instead of guessing."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_text_splitters import RecursiveCharacterTextSplitter

from core import db, prompts
from core.guardrails import check_question
from core.llm import get_llm

TOKEN = re.compile(r"[a-z0-9]+")
STOP = set("the a an and or to of in on for is are was were be we i you it that this with at by from as what who "
           "which when where how did does do any all about".split())
NOT_FOUND = "I couldn't find that information in the records."
_SPLITTER = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120, separators=["\n\n", "\n", ". ", " ", ""])


def _tok(t: str) -> list[str]:
    return [w for w in TOKEN.findall(t.lower()) if w not in STOP]


def chunk_text(text: str) -> list[str]:
    return _SPLITTER.split_text(text)


def index_record(record_id: int, text: str) -> int:
    chunks = chunk_text(text)
    db.save_chunks(record_id, chunks, get_llm().embed(chunks))
    return len(chunks)


def _bm25(query: list[str], docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> list[float]:
    n = len(docs)
    avgdl = sum(len(d) for d in docs) / max(n, 1)
    df = Counter(w for d in docs for w in set(d))
    scores = []
    for d in docs:
        tf = Counter(d)
        s = 0.0
        for w in query:
            if w in tf:
                idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * len(d) / max(avgdl, 1)))
        scores.append(s)
    return scores


class HybridRetriever(BaseRetriever):
    """LangChain retriever over the SQLite chunk store (persistent, per use case)."""
    record_ids: list[int] | None = None
    k: int = 5
    min_score: float = 0.05
    vector_weight: float = 0.5

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> list[Document]:
        rows = db.load_chunks(self.record_ids)
        if not rows:
            return []
        bm = np.array(_bm25(_tok(query), [_tok(r["text"]) for r in rows]))
        score = bm / bm.max() if bm.max() > 0 else bm
        if all(r["embedding"] for r in rows):
            qe = get_llm().embed([query])
            if qe:
                m = np.array([r["embedding"] for r in rows], dtype=float)
                v = np.array(qe[0], dtype=float)
                cos = m @ v / (np.linalg.norm(m, axis=1) * np.linalg.norm(v) + 1e-9)
                score = (1 - self.vector_weight) * score + self.vector_weight * cos
        order = np.argsort(-score)[: self.k]
        return [Document(page_content=rows[i]["text"],
                         metadata={"record_id": rows[i]["record_id"], "idx": rows[i]["idx"], "title": rows[i]["title"],
                                   "score": float(score[i]), "cite": f"R{rows[i]['record_id']}#{rows[i]['idx']}"})
                for i in order if score[i] > self.min_score]


@dataclass
class Hit:
    record_id: int
    idx: int
    title: str
    text: str
    score: float

    @property
    def cite(self) -> str:
        return f"R{self.record_id}#{self.idx}"


@dataclass
class Answer:
    text: str
    hits: list[Hit] = field(default_factory=list)
    provider: str = ""
    refused: bool = False


def _format(docs: list[Document]) -> str:
    return "\n".join(f"[{d.metadata['cite']}]\n{d.page_content}" for d in docs)


def _generate(inputs: dict) -> dict:
    docs: list[Document] = inputs["docs"]
    if not docs:
        return {"text": NOT_FOUND, "docs": docs, "provider": ""}
    system, user_t, _ = prompts.load("answer")
    res = get_llm().chat("answer", system, prompts.render(user_t, question=inputs["question"], context=_format(docs)))
    return {"text": res.text, "docs": docs, "provider": res.provider + (" (fallback)" if res.fallback_used else "")}


def build_chain(record_ids: list[int] | None = None):
    """LCEL RAG chain:  {docs: retriever, question: passthrough} -> generate"""
    retriever = HybridRetriever(record_ids=record_ids)
    return {"docs": retriever, "question": RunnablePassthrough()} | RunnableLambda(_generate)


def retrieve(question: str, record_ids: list[int] | None = None, k: int = 5) -> list[Hit]:
    docs = HybridRetriever(record_ids=record_ids, k=k).invoke(question)
    return [Hit(d.metadata["record_id"], d.metadata["idx"], d.metadata["title"], d.page_content, d.metadata["score"])
            for d in docs]


def ask(question: str, record_ids: list[int] | None = None) -> Answer:
    if reason := check_question(question):
        return Answer(reason, refused=True)
    out = build_chain(record_ids).invoke(question)
    hits = [Hit(d.metadata["record_id"], d.metadata["idx"], d.metadata["title"], d.page_content, d.metadata["score"])
            for d in out["docs"]]
    return Answer(out["text"], hits, out["provider"])
