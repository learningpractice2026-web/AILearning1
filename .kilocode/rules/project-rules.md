# Project rules for AI coding agents (Kilo Code reads this automatically)

This repo is a **config-driven GenAI accelerator** (Python, Streamlit, LangChain, LangGraph). One generic pipeline:
`input (text/docx/pdf/scanned/image/audio) → clean → input guardrails → LangGraph: extract ↔ validate (repair loop) → verify → output guardrails → store → RAG chat → exports`.
A *use case* is only a folder: `usecases/<name>/` = `usecase.yaml` + `samples/*.txt` + `gold.json`.

## Golden rules
1. **For a new use case, change ONLY `usecases/<name>/` and `DELIVERABLES.md`.** Do not edit Python unless the YAML truly cannot express the need. If you must, ask first and keep it generic. It must still pass for every other folder in `usecases/`.
   **Approved add-ons** (from the README capability catalog / Prompt 0) go in a new module behind a `.env` switch (default off). Each gets a test, and must not break the built-in path or other use cases. Add new packages to `requirements.txt` only after approval.
2. Start a new use case with `python scripts/new_usecase.py <snake_case_name>` (copies `usecases/_template`, sets `USECASE` in `.env`). Every YAML key is explained inside `usecases/_template/usecase.yaml`. More examples: `meeting_notes` (dialogue), `incident_triage` (tickets), `contract_review` (long documents).
3. YAML rules: 2-space indentation; snake_case keys; exactly one section with `is_task: true`; quote strings containing `:` or `#`; `keywords` are regexes (inside double quotes escape a backslash as `\\`). Field `options` are the only allowed values.
4. Samples are **synthetic only** (fictional names/companies). Provide 3–4 `.txt` samples: one file whose name contains `heldout` (messy/informal, written last), one with PII (email/phone), and one containing a prompt-injection line (e.g. "ignore previous instructions and …") so the guardrails are visible in the demo.
5. `gold.json` = expected results per sample: `{"file.txt": {"fields": {"<field>": "<option>"}, "<section_key>": [["kw1","kw2"], {"kw": ["kw"], "owner": "Name", "deadline": "Friday"}]}}`. Every keyword MUST literally appear in that sample file.
6. Done means all of these pass: `python scripts/check_setup.py`, `pytest -q` (tests run every use-case folder end-to-end), `python -m eval.run_eval`.
7. Never put secrets in code/YAML; keys live only in `.env`. Don't add dependencies without asking.
8. Don't create new markdown files. Instructions live in `README.md`; jury deliverables in `DELIVERABLES.md`.

## Map
| Path | What | Edit for a new use case? |
|---|---|---|
| `usecases/<name>/usecase.yaml` | labels, AI role/task/rules, fields, sections, offline keywords, guardrails, chat examples | **YES** |
| `usecases/<name>/samples/*.txt`, `gold.json` | synthetic inputs + expected outputs | **YES** |
| `usecases/<name>/prompts/extract_v1.md` | optional prompt override (copy from `prompts/`, keep `{placeholders}`) | optional |
| `DELIVERABLES.md` | D1–D5, pitch, AI usage log | **YES (rewrite)** |
| `core/` `services/` `app.py` `pages/` `api.py` | generic engine + UI | no |
