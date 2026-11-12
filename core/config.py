"""Central configuration. Every setting comes from environment variables (12-factor),
so the same image runs locally, in Docker, or on AKS without code changes."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT_DIR / "prompts"


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # ---- LLM provider: openai | azure | gemini | ollama | mock ----
    llm_provider: str
    api_key: str
    base_url: str
    azure_api_version: str
    model_fast: str          # cheap/small model (router default)
    model_strong: str        # bigger model for long / complex inputs
    embed_model: str         # empty -> local BM25 only
    stt_model: str           # speech-to-text model (whisper-1 etc.)
    vision_model: str        # multimodal model for images / scanned PDFs (blank = model_strong)
    use_langgraph: bool      # orchestrate the pipeline as a LangGraph state graph
    extra_headers: str       # JSON dict of extra HTTP headers some enterprise gateways need
    ca_bundle: str           # path to corporate CA certificate (.pem) if SSL inspection breaks HTTPS
    max_parallel: int        # concurrent chunk extractions for large documents
    router_threshold_chars: int
    max_chars_per_call: int
    fallback_to_mock: bool   # graceful degradation if provider fails
    # ---- cost / budget ----
    price_in_per_1k: float
    price_out_per_1k: float
    daily_token_budget: int
    # ---- app ----
    db_path: str
    auth_enabled: bool
    app_users: str           # "user:password:role,..."
    mask_pii_default: bool


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        llm_provider=os.getenv("LLM_PROVIDER", "mock").lower(),
        api_key=os.getenv("LLM_API_KEY", ""),
        base_url=os.getenv("LLM_BASE_URL", ""),
        azure_api_version=os.getenv("AZURE_API_VERSION", "2024-10-21"),
        model_fast=os.getenv("LLM_MODEL_FAST", "gpt-4o-mini"),
        model_strong=os.getenv("LLM_MODEL_STRONG", "gpt-4o"),
        embed_model=os.getenv("EMBED_MODEL", ""),
        stt_model=os.getenv("STT_MODEL", "whisper-1"),
        vision_model=os.getenv("VISION_MODEL", ""),
        use_langgraph=_bool("USE_LANGGRAPH", True),
        extra_headers=os.getenv("LLM_EXTRA_HEADERS", ""),
        ca_bundle=os.getenv("LLM_CA_BUNDLE", ""),
        max_parallel=int(os.getenv("MAX_PARALLEL", "4")),
        router_threshold_chars=int(os.getenv("ROUTER_THRESHOLD_CHARS", "12000")),
        max_chars_per_call=int(os.getenv("MAX_CHARS_PER_CALL", "24000")),
        fallback_to_mock=_bool("FALLBACK_TO_MOCK", True),
        price_in_per_1k=float(os.getenv("PRICE_IN_PER_1K", "0.00015")),
        price_out_per_1k=float(os.getenv("PRICE_OUT_PER_1K", "0.0006")),
        daily_token_budget=int(os.getenv("DAILY_TOKEN_BUDGET", "500000")),
        db_path=os.getenv("DB_PATH") or str(ROOT_DIR / "data" / f"{os.getenv('USECASE', 'meeting_notes')}.db"),
        auth_enabled=_bool("AUTH_ENABLED", False),
        app_users=os.getenv("APP_USERS", "admin:admin123:admin,lead:lead123:editor,viewer:view123:viewer"),
        mask_pii_default=_bool("MASK_PII_DEFAULT", True),
    )
