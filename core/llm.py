"""LLM gateway built on LangChain.

- Models:    langchain_openai.ChatOpenAI / AzureChatOpenAI — covers the TCS-provided gateway (OpenAI-compatible
             or Azure), OpenAI, Gemini (OpenAI-compatible endpoint) and Ollama. Switch in .env, no code change.
- Chains:    LCEL  `ChatPromptTemplate | chat_model`  (usage_metadata gives tokens for cost tracking)
- Caching:   LangChain global LLM cache (`set_llm_cache`) with a SQLite-backed `BaseCache` implementation
- Router:    fast model by default, strong model for long / complex inputs
- Resilience: retries with backoff, JSON-mode auto-downgrade for gateways that reject response_format,
             daily token budget, graceful fallback to the offline rules engine
- Observability: every call logged (task, model, tokens, cost, latency, cached, errors) -> Admin page
- Enterprise network: optional custom headers (LLM_EXTRA_HEADERS) and corporate CA bundle (LLM_CA_BUNDLE)
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any, Sequence

from core import db, mock_engine
from core.config import Settings, get_settings
from core.logging_setup import get_logger

log = get_logger("llm")

GEMINI_OPENAI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
OLLAMA_URL = "http://localhost:11434/v1"
_hit = threading.local()


class BudgetExceeded(RuntimeError):
    pass


# --------------------------------------------------------------------------- LangChain cache
def _make_sqlite_cache(path: str):
    """SQLite implementation of LangChain's BaseCache (langchain_core only — no deprecated community pkg)."""
    from langchain_core.caches import BaseCache
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration

    class SQLiteLLMCache(BaseCache):
        """Stores only the response text + token usage (plain JSON, no object deserialisation = safe)."""

        def __init__(self, db_path: str):
            self.db_path = db_path
            with sqlite3.connect(db_path) as c:
                c.execute("CREATE TABLE IF NOT EXISTS lc_cache (prompt TEXT, llm TEXT, value TEXT, "
                          "PRIMARY KEY (prompt, llm))")

        def lookup(self, prompt: str, llm_string: str):
            with sqlite3.connect(self.db_path) as c:
                r = c.execute("SELECT value FROM lc_cache WHERE prompt=? AND llm=?", (prompt, llm_string)).fetchone()
            if not r:
                return None
            _hit.flag = True
            return [ChatGeneration(message=AIMessage(content=g["text"], usage_metadata=g.get("usage")))
                    for g in json.loads(r[0])]

        def update(self, prompt: str, llm_string: str, return_val: Sequence) -> None:
            gens = [{"text": g.text, "usage": getattr(getattr(g, "message", None), "usage_metadata", None)}
                    for g in return_val]
            with sqlite3.connect(self.db_path) as c:
                c.execute("INSERT OR REPLACE INTO lc_cache VALUES (?,?,?)", (prompt, llm_string, json.dumps(gens)))

        def clear(self, **kwargs: Any) -> None:
            with sqlite3.connect(self.db_path) as c:
                c.execute("DELETE FROM lc_cache")

    return SQLiteLLMCache(path)


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    cached: bool = False
    fallback_used: bool = False
    latency_ms: int = 0


class LLMGateway:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or get_settings()
        self.provider = self.s.llm_provider
        self._models: dict[str, Any] = {}
        self._json_supported = True
        if self.provider != "mock":
            try:
                from langchain_core.globals import set_llm_cache
                db.init_db()
                set_llm_cache(_make_sqlite_cache(self.s.db_path))
                self._model(self.s.model_fast)  # fail fast on bad config
            except Exception as e:  # missing package / bad config -> degrade, never crash the app
                log.error(f"LLM init failed, using offline engine: {e}")
                self.init_error = str(e)
                self.provider = "mock"

    # ------------------------------------------------------------------ models
    def _http_kwargs(self) -> dict:
        kw: dict[str, Any] = {}
        if self.s.extra_headers:
            kw["default_headers"] = json.loads(self.s.extra_headers)
        if self.s.ca_bundle:
            import httpx
            kw["http_client"] = httpx.Client(verify=self.s.ca_bundle, timeout=120)
        return kw

    def _model(self, name: str, **extra):
        key = f"{name}|{json.dumps(extra, sort_keys=True)}"
        if key not in self._models:
            common = dict(temperature=extra.pop("temperature", 0.1), max_retries=1, timeout=120, **self._http_kwargs())
            if self.provider == "azure":
                from langchain_openai import AzureChatOpenAI
                m = AzureChatOpenAI(azure_deployment=name, azure_endpoint=self.s.base_url, api_key=self.s.api_key,
                                    api_version=self.s.azure_api_version, **common)
            else:
                from langchain_openai import ChatOpenAI
                base = self.s.base_url or {"gemini": GEMINI_OPENAI_URL, "ollama": OLLAMA_URL}.get(self.provider)
                m = ChatOpenAI(model=name, api_key=self.s.api_key or "not-needed", base_url=base or None, **common)
            self._models[key] = m
        return self._models[key]

    @property
    def label(self) -> str:
        if self.provider == "mock":
            return "mock (offline rules engine)"
        return f"{self.provider} via LangChain: {self.s.model_fast} / {self.s.model_strong}"

    # ------------------------------------------------------------------ router
    def route(self, task: str, prompt_chars: int) -> str:
        """Cheapest model that meets the need: long or complex extraction -> strong model."""
        if task in {"extract", "summarize"} and prompt_chars > self.s.router_threshold_chars:
            return self.s.model_strong
        return self.s.model_fast

    # -------------------------------------------------------------------- chat
    def chat(self, task: str, system: str, user: str, json_mode: bool = False,
             temperature: float = 0.1, use_cache: bool = True) -> LLMResult:
        if self.provider == "mock":
            return self._mock(task, user)
        model_name = self.route(task, len(system) + len(user))
        try:
            if db.tokens_used_today() > self.s.daily_token_budget:
                raise BudgetExceeded("Daily token budget exhausted")
            text, pt, ct, ms, cached = self._invoke(model_name, system, user, json_mode, temperature, use_cache)
            cost = 0.0 if cached else pt / 1000 * self.s.price_in_per_1k + ct / 1000 * self.s.price_out_per_1k
            db.log_llm_call(task=task, provider=self.provider, model=model_name, prompt_tokens=0 if cached else pt,
                            completion_tokens=0 if cached else ct, latency_ms=ms, cached=cached,
                            cost_usd=round(cost, 6))
            return LLMResult(text, self.provider, model_name, cached=cached, latency_ms=ms)
        except Exception as e:
            db.log_llm_call(task=task, provider=self.provider, model=model_name, status="error", error=str(e)[:300])
            log.error(f"LLM call failed ({task}): {e}")
            if self.s.fallback_to_mock:
                res = self._mock(task, user)
                res.fallback_used = True
                return res
            raise

    def _invoke(self, model_name, system, user, json_mode, temperature, use_cache, attempts: int = 2):
        from langchain_core.prompts import ChatPromptTemplate
        prompt = ChatPromptTemplate.from_messages([("system", "{system}"), ("human", "{user}")])
        last: Exception | None = None
        for i in range(attempts):
            llm = self._model(model_name, temperature=temperature)
            if not use_cache:
                llm = llm.model_copy(update={"cache": False})
            if json_mode and self._json_supported:
                llm = llm.bind(response_format={"type": "json_object"})
            chain = prompt | llm  # LCEL
            _hit.flag = False
            t0 = time.perf_counter()
            try:
                msg = chain.invoke({"system": system, "user": user})
                ms = int((time.perf_counter() - t0) * 1000)
                usage = getattr(msg, "usage_metadata", None) or {}
                return (msg.content if isinstance(msg.content, str) else str(msg.content),
                        usage.get("input_tokens", 0), usage.get("output_tokens", 0), ms, bool(_hit.flag))
            except Exception as e:  # rate limit / timeout / gateway quirks
                last = e
                if json_mode and "response_format" in str(e).lower() and self._json_supported:
                    log.info("Gateway rejected response_format; retrying with prompt-only JSON")
                    self._json_supported = False
                    continue
                time.sleep(min(2 ** i, 8))
        raise last  # type: ignore[misc]

    def _mock(self, task: str, user: str) -> LLMResult:
        t0 = time.perf_counter()
        text = mock_engine.respond(task, user)
        ms = int((time.perf_counter() - t0) * 1000)
        db.log_llm_call(task=task, provider="mock", model="rules", latency_ms=ms)
        return LLMResult(text, "mock", "rules", latency_ms=ms)

    # ------------------------------------------------------------- embeddings
    def embedder(self):
        """LangChain Embeddings object, or None (retrieval then uses BM25 only)."""
        if self.provider == "mock" or not self.s.embed_model:
            return None
        if "embed" not in self._models:
            if self.provider == "azure":
                from langchain_openai import AzureOpenAIEmbeddings
                self._models["embed"] = AzureOpenAIEmbeddings(
                    azure_deployment=self.s.embed_model, azure_endpoint=self.s.base_url, api_key=self.s.api_key,
                    api_version=self.s.azure_api_version, **self._http_kwargs())
            else:
                from langchain_openai import OpenAIEmbeddings
                base = self.s.base_url or {"gemini": GEMINI_OPENAI_URL, "ollama": OLLAMA_URL}.get(self.provider)
                self._models["embed"] = OpenAIEmbeddings(
                    model=self.s.embed_model, api_key=self.s.api_key or "not-needed", base_url=base or None,
                    check_embedding_ctx_length=False, **self._http_kwargs())
        return self._models["embed"]

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        emb = self.embedder()
        if emb is None or not texts:
            return None
        try:
            t0 = time.perf_counter()
            vecs = emb.embed_documents(texts)
            db.log_llm_call(task="embed", provider=self.provider, model=self.s.embed_model,
                            latency_ms=int((time.perf_counter() - t0) * 1000))
            return vecs
        except Exception as e:
            log.error(f"Embedding failed, using BM25 only: {e}")
            return None

    # --------------------------------------------------------- speech-to-text
    def transcribe(self, path: str) -> str:
        """Whisper through the same configured endpoint (LangChain model's underlying client),
        else local faster-whisper if installed."""
        if self.provider in {"openai", "azure"}:
            client = self._model(self.s.model_fast).root_client
            with open(path, "rb") as f:
                return client.audio.transcriptions.create(model=self.s.stt_model, file=f).text
        try:
            from faster_whisper import WhisperModel  # optional: pip install faster-whisper
            segments, _ = WhisperModel("base", device="cpu", compute_type="int8").transcribe(path)
            return "\n".join(seg.text.strip() for seg in segments)
        except ImportError as e:
            raise RuntimeError("Audio needs LLM_PROVIDER=openai/azure with a Whisper model (STT_MODEL), or "
                               "`pip install faster-whisper`. Upload a text transcript instead.") from e

    # ------------------------------------------------------------ multimodal
    def vision_to_text(self, images: list[tuple[bytes, str]], instruction: str = "") -> str:
        """Images / scanned pages -> faithful text via a multimodal chat model (LangChain content blocks)."""
        if self.provider == "mock":
            raise RuntimeError("Images and scanned PDFs need a vision model: set LLM_PROVIDER and VISION_MODEL "
                               "in .env, or upload a text file instead.")
        import base64

        from langchain_core.messages import HumanMessage
        content: list[dict] = [{"type": "text", "text": instruction or (
            "Transcribe ALL text in these images exactly, preserving line breaks, speaker names, tables "
            "(as markdown) and numbers. Then, under 'VISUAL NOTES:', briefly describe any diagrams, charts, "
            "stamps or handwriting. Do not add facts that are not visible.")}]
        for data, mime in images:
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{base64.b64encode(data).decode()}"}})
        model_name = self.s.vision_model or self.s.model_strong
        t0 = time.perf_counter()
        msg = self._model(model_name, temperature=0).invoke([HumanMessage(content=content)])
        usage = getattr(msg, "usage_metadata", None) or {}
        pt, ct = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        db.log_llm_call(task="vision", provider=self.provider, model=model_name, prompt_tokens=pt, completion_tokens=ct,
                        latency_ms=int((time.perf_counter() - t0) * 1000),
                        cost_usd=round(pt / 1000 * self.s.price_in_per_1k + ct / 1000 * self.s.price_out_per_1k, 6))
        return msg.content if isinstance(msg.content, str) else str(msg.content)


_gateway: LLMGateway | None = None


def get_llm() -> LLMGateway:
    global _gateway
    if _gateway is None:
        _gateway = LLMGateway()
    return _gateway
