"""Checks everything a non-Python user needs, in plain words. Run:  python scripts/check_setup.py
(or double-click 2_check_setup.bat on Windows)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

OK, BAD, WARN = "[ OK ]", "[FAIL]", "[WARN]"
problems = 0


def say(tag: str, msg: str, fix: str = "") -> None:
    global problems
    print(f"{tag} {msg}")
    if fix:
        print(f"       -> How to fix: {fix}")
    if tag == BAD:
        problems += 1


print("=" * 70)
print(" AI Friday Accelerator - setup check")
print("=" * 70)

# 1. Python
v = sys.version_info
if v >= (3, 10):
    say(OK, f"Python {v.major}.{v.minor} found")
else:
    say(BAD, f"Python {v.major}.{v.minor} is too old", "Install Python 3.11 or 3.12 from python.org (tick 'Add to PATH')")

# 2. Packages
missing = []
for mod, pkg in [("streamlit", "streamlit"), ("openai", "openai"), ("pydantic", "pydantic"), ("yaml", "pyyaml"),
                 ("dotenv", "python-dotenv"), ("pandas", "pandas"), ("docx", "python-docx"), ("pypdf", "pypdf"),
                 ("reportlab", "reportlab"), ("fastapi", "fastapi"), ("langchain_core", "langchain-core"),
                 ("langchain_openai", "langchain-openai"), ("langchain_text_splitters", "langchain-text-splitters"),
                 ("langgraph", "langgraph"), ("pypdfium2", "pypdfium2"), ("PIL", "pillow")]:
    try:
        __import__(mod)
    except ImportError:
        missing.append(pkg)
if missing:
    say(BAD, f"Missing packages: {', '.join(missing)}", "Run 1_setup.bat again (or: pip install -r requirements.txt)")
    sys.exit(1)
say(OK, "All Python packages installed (incl. LangChain, LangGraph)")

# 3. .env
if (ROOT / ".env").exists():
    say(OK, ".env file found")
else:
    say(WARN, ".env not found - using defaults (offline mock mode)", "Copy .env.example to .env and edit it")

from core.config import get_settings  # noqa: E402
from core.usecase import USECASES_DIR, get_usecase  # noqa: E402

# 4. Use case
try:
    uc = get_usecase()
    n = len(list(uc.samples_dir.glob("*.txt"))) if uc.samples_dir.exists() else 0
    say(OK, f"Use case '{uc.slug}' loaded: '{uc.app.name}', {len(uc.sections)} sections, {n} sample files")
    if n == 0:
        say(WARN, "No sample files", f"Add .txt files to usecases/{uc.slug}/samples/")
except Exception as e:  # noqa: BLE001
    names = [p.name for p in USECASES_DIR.iterdir() if (p / "usecase.yaml").exists() and not p.name.startswith("_")]
    say(BAD, f"Use case could not be loaded: {e}",
        f"Check USECASE in .env (available: {', '.join(names)}) and the YAML indentation (spaces, not tabs)")
    sys.exit(1)

# 5. LLM connection
s = get_settings()
if s.llm_provider == "mock":
    say(WARN, "LLM_PROVIDER=mock -> offline rules engine, no real AI",
        "For the real demo set LLM_PROVIDER and LLM_API_KEY in .env (see README.md, Part 1 Step 3)")
else:
    from core import db
    from core.llm import LLMGateway
    db.init_db()
    if not s.api_key and s.llm_provider != "ollama":
        say(BAD, f"LLM_PROVIDER={s.llm_provider} but LLM_API_KEY is empty", "Paste your key into .env")
    else:
        g = LLMGateway(s.__class__(**{**s.__dict__, "fallback_to_mock": False}))
        if g.provider == "mock":
            say(BAD, f"Could not create the LangChain model: {getattr(g, 'init_error', 'unknown error')}",
                "Check LLM_PROVIDER / LLM_BASE_URL / LLM_EXTRA_HEADERS (must be valid JSON) in .env")
            sys.exit(1)
        say(OK, f"LangChain model ready: {g.label}")
        try:
            r = g.chat("healthcheck", "Reply with the single word OK.", "Say OK", use_cache=False)
            say(OK, f"AI call works: provider={r.provider}, model={r.model}, reply='{r.text.strip()[:30]}', {r.latency_ms} ms")
            r2 = g.chat("healthcheck", 'Return JSON {"ok": true}', "json please", json_mode=True, use_cache=False)
            say(OK if "ok" in r2.text.lower() else WARN, f"JSON mode works: {r2.text.strip()[:40]}")
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            hint = "Check LLM_API_KEY / LLM_BASE_URL / model names in .env"
            if "401" in msg or "auth" in msg.lower():
                hint = "API key is wrong or expired"
            elif "404" in msg or "not found" in msg.lower():
                hint = ("Model / deployment name not found. Azure: LLM_MODEL_FAST must be your DEPLOYMENT name; "
                        "also check LLM_BASE_URL")
            elif "429" in msg:
                hint = "Rate limit / quota exceeded - wait a minute or use another key"
            elif "connect" in msg.lower() or "timeout" in msg.lower():
                hint = "Network blocked (office proxy/VPN?) - try mobile hotspot, or check LLM_BASE_URL"
            say(BAD, f"AI call failed: {msg[:200]}", hint)
        if s.embed_model:
            emb = g.embed(["hello"])
            say(OK if emb else WARN, f"Embeddings {'work' if emb else 'failed - chat will use keyword search only'}"
                f" (EMBED_MODEL={s.embed_model})")
        else:
            say(WARN, "EMBED_MODEL empty -> chat uses keyword (BM25) search only. That is fine for the demo.")

print("=" * 70)
print(" RESULT:", "ALL GOOD - run 3_run_app.bat" if problems == 0 else f"{problems} problem(s) - fix the [FAIL] lines above")
print("=" * 70)
sys.exit(1 if problems else 0)
