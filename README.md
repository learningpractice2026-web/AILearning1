# 🧠 AI Friday Accelerator: one template for any enterprise GenAI use case

> **This README is the only guide you need.** Read it top to bottom once. No Python knowledge required.
> The only other document is `DELIVERABLES.md`, which holds the jury deliverables (D1–D5 + pitch) that Kilo Code writes for you.

**What it does:** you give it messy input (text, Word, PDF, scanned PDF, image, audio). It returns verified, structured output, then lets a human review and approve it, chat over it, and export it.
**How it adapts:** each use case is one folder of settings, `usecases/<name>/`. You don't change any code. Kilo Code creates that folder from your problem statement.

**Built with:** Python · Streamlit (UI) · **LangChain** (LLM models, LCEL chains, text splitter, retriever, LLM cache) · **LangGraph** (agent workflow with a self-repair loop) · FastAPI (REST) · SQLite · TCS LLM API (or OpenAI / Azure / Gemini / Ollama).

---

## Contents
1. [One-time setup](#part-1--one-time-setup-20-min-do-it-before-the-hackathon)
2. [See the demo with the sample use case](#part-2--see-the-demo-5-min)
3. [How it works](#part-3--how-it-works-explain-this-to-the-jury)
4. [Hackathon day: build YOUR use case with Kilo Code](#part-4--hackathon-day-build-your-use-case-with-kilo-code) (capability catalog, tech-stack selector prompt, master prompt)
5. [Demo-day checklist](#part-5--demo-day-checklist)
6. [Troubleshooting](#part-6--troubleshooting)
7. [Reference](#part-7--reference)

---

## Part 1 — One-time setup (20 min, do it before the hackathon)

### Step 1. Install Python 3.12
1. Download **Python 3.12** for Windows from https://www.python.org/downloads/ and run the installer.
2. ⚠️ On the first screen, **tick "Add python.exe to PATH"**, then click *Install Now*.
3. To check it: press `Win + R`, type `cmd`, press Enter, then type `python --version`. You should see `Python 3.12.x`.
   - If the Microsoft Store opens or you get "not recognized": go to *Settings → Apps → Advanced app settings → App execution aliases*, switch **off** `python.exe` and `python3.exe`, reinstall with the PATH box ticked, and reopen cmd.

### Step 2. Get the code and install it → double-click `1_setup.bat`
Get the code in one of two ways:
- **No Git:** on the GitHub page click the green **Code** button → **Download ZIP**, then right-click the zip → *Extract All* into a simple path such as `C:\AI\AILearning1`.
- **With Git:** `git clone https://github.com/learningpractice2026-web/AILearning1.git`

Open the extracted folder and double-click **`1_setup.bat`**.
It creates a private Python environment (`.venv`), installs everything (2–5 min) and creates your settings file `.env`.
- ✅ The last line says `SETUP DONE`.
- ❌ If it says "Package install FAILED", switch to a mobile hotspot (office networks often block downloads) and run it again.

### Step 3. Put the TCS LLM API key in `.env`
Open the folder in VS Code (*File → Open Folder*). Click the file **`.env`** in the left panel (a name starting with a dot is normal).

First, get these details from whoever gave you the TCS key: **(a) endpoint URL, (b) model name(s), (c) is it Azure OpenAI or OpenAI-compatible, (d) do they need a special header?** Then set the matching lines and save with `Ctrl+S`:

| Your key is… | Set these lines in `.env` |
|---|---|
| **TCS gateway, OpenAI-compatible** (URL usually ends in `/v1`) | `LLM_PROVIDER=openai`<br>`LLM_API_KEY=<TCS key>`<br>`LLM_BASE_URL=<TCS endpoint URL>`<br>`LLM_MODEL_FAST=<small model name>`<br>`LLM_MODEL_STRONG=<big model name>` (same name is fine)<br>`EMBED_MODEL=<embedding model name>` (blank if you don't have one) |
| **TCS Azure OpenAI resource** (URL like `https://xxx.openai.azure.com/`) | `LLM_PROVIDER=azure`<br>`LLM_API_KEY=<key>`<br>`LLM_BASE_URL=https://xxx.openai.azure.com/`<br>`LLM_MODEL_FAST=<DEPLOYMENT name>` ⚠️ deployment name, not model name<br>`LLM_MODEL_STRONG=<deployment name>`<br>`EMBED_MODEL=<embedding deployment>` (optional)<br>`AZURE_API_VERSION=2024-10-21` (or the version they give) |
| Gateway needs a **special header** | add `LLM_EXTRA_HEADERS={"x-api-key": "<key>"}` (use the header name they give you) |
| **SSL / certificate errors** on the office network | `LLM_CA_BUNDLE=C:\path\to\company-root-certificate.pem` |
| OpenAI key (`sk-…`) | `LLM_PROVIDER=openai`, `LLM_API_KEY=sk-…`, `LLM_MODEL_FAST=gpt-4o-mini`, `LLM_MODEL_STRONG=gpt-4o`, `EMBED_MODEL=text-embedding-3-small` |
| Gemini key | `LLM_PROVIDER=gemini`, `LLM_API_KEY=…`, `LLM_MODEL_FAST=gemini-2.5-flash`, `LLM_MODEL_STRONG=gemini-2.5-pro` |
| No key / no internet (backup) | `LLM_PROVIDER=mock` (offline keyword engine: less accurate, but the demo never dies) |

Optional: `VISION_MODEL=` a multimodal model (e.g. gpt-4o) for images and scanned PDFs. `STT_MODEL=` a Whisper model for audio.
🔒 Never share or commit `.env`. It is already excluded from Git.

### Step 4. Test the key → double-click `2_check_setup.bat`
It checks Python, the packages, `.env` and the use case, then makes **one tiny AI call**.
- ✅ You see `[ OK ] AI call works …` and **ALL GOOD**.
- ❌ Each `[FAIL]` line tells you what to fix (wrong key, wrong deployment name, blocked network…). Fix `.env`, save, and run it again.

### Step 5. Start the app → double-click `3_run_app.bat`
Your browser opens **http://localhost:8501**. Keep the black window open; closing it stops the app.

---

## Part 2 — See the demo (5 min)
The default use case is `meeting_notes`, and its sample data is loaded automatically.
1. **Upload** (left menu) → tab *Sample data* → pick `architecture_review.txt` → **Analyse with AI**. You will see the live steps of the LangGraph pipeline, then:
   🛡️ PII masked · 🚨 prompt-injection warning · grounding rate · decisions / action items / risks / questions.
2. **Review and Export** → *Review & approve*: fix an owner, click **Save & approve**. Then in *Export*: download a Jira CSV, Word, PDF or email draft.
3. **Chat** → "Who owns the PII masking work and by when?" → the answer has source citations like `[R1#0]`.
4. **Dashboard** → metrics and charts.
5. **Admin** → AI calls, tokens, cost, cache hits, latency, the LangGraph **pipeline diagram**, feedback and audit log.

To try the other example use cases, set `USECASE=incident_triage` or `USECASE=contract_review` in `.env`, save, close the black window and double-click `3_run_app.bat` again.

---

## Part 3 — How it works (explain this to the jury)

```
Upload (txt / docx / pdf / scanned pdf / image / audio)
   │  multimodal ingestion: pypdf text · vision model for scans & images · Whisper for audio
   ▼
┌──────────────────────── LangGraph state graph ─────────────────────────────┐
│ clean → guard_input → extract ──► validate ──ok──► verify → guard_output → store │
│ (PII mask, injection)     ▲  │        │ invalid                    (PII leak,   │ (DB + RAG index)
│                           └──┼────────┘ repair loop (max 2)         blocked     │
│   long input: LangChain      │          then → fallback (offline)   terms)      │
│   splitter → parallel map-reduce ─────────────► verify                          │
└──────────────────────────────────────────────────────────────────────────────┘
   ▼
Human review & approve → Dashboard · Chat (LangChain hybrid retriever + LCEL RAG chain, citations) · Exports · REST API
```

| Enterprise capability | How it is done | File |
|---|---|---|
| Model switch / multi-model | `.env` picks TCS gateway, Azure, OpenAI, Gemini or Ollama. Router sends long inputs to the strong model and the rest to the fast, cheap one | `core/llm.py` |
| LangChain | `ChatOpenAI` / `AzureChatOpenAI`, LCEL chains (`prompt \| model`), `RecursiveCharacterTextSplitter`, `BaseRetriever`, LLM cache, `.batch()` parallelism | `core/llm.py`, `services/rag.py`, `services/extractor.py` |
| LangGraph | Agent workflow: Extractor → Validator (self-repair loop) → Verifier → Guards, with fallback | `services/graph.py` |
| Chunking & large documents | Splitter with overlap → chunks processed in parallel (concurrency cap) → merge + de-duplicate → summary of summaries | `services/extractor.py` |
| Caching | LangChain global LLM cache, SQLite-backed (repeat calls cost ₹0 and are instant) | `core/llm.py` |
| PDF / multimodal | Digital PDF text + tables from Word. Scanned pages and images go to the vision model. Audio goes to Whisper | `services/ingest.py` |
| Guardrails & security | Input: PII masking, prompt-injection detection, size limit. Output: PII re-mask, blocked terms, reliability check. Evidence quote per item, plus a verifier. Login roles, audit log, token budget | `core/guardrails.py`, `services/extractor.py`, `ui/common.py` |
| RAG | Hybrid BM25 + embeddings retriever, answers cite sources and say "not found" instead of guessing | `services/rag.py` |
| Human-in-the-loop | Editable review tables, approve before export | `pages/2_Review_and_Export.py` |
| Observability & cost | Every call logged with tokens, cost, latency and cache hit; daily budget; 👍/👎 feedback | `pages/4_Admin.py` |
| Evaluation (D4 evidence) | Gold set + held-out sample, recall / owner / field accuracy | `eval/run_eval.py` |
| API & deployment | FastAPI with Swagger, Docker, CI | `api.py`, `Dockerfile` |

---

## Part 4 — Hackathon day: build YOUR use case with Kilo Code

**The idea:** the engine, UI, guardrails, RAG and exports are already done and tested. For your problem statement Kilo only writes **one folder** (`usecases/<name>/`) plus `DELIVERABLES.md`. A built-in test then runs your new use case end-to-end to prove it works.

### Before you start (2 min)
1. Open the project folder in VS Code and open Kilo Code from the left sidebar. Choose a strong model and **Code** mode.
2. Kilo automatically reads the project rules in `.kilocode/rules/project-rules.md`.

### Timeline (official session 10:00–4:00)
| Time | What | Who (hat) | How |
|---|---|---|---|
| 10:00–10:30 | Pick the case; agree problem, users, success measures, riskiest assumption, **tech stack** | All (Problem lead drives) | **Prompt 0** (tech-stack selector) → agree stack. Then **Prompt 1** → Kilo does **Phase 1** (design only). Discuss it and correct Kilo. |
| 10:30–11:20 | Architecture options & decision (25 marks!) | Architecture lead | Discuss 3 options as a team. Ask a reasoning model with **Prompt 5**. The team makes the final call. |
| 10:30–11:30 | Build | POC lead + Integrator | Type `next phase` → **Phase 2**: Kilo creates the folder and samples, then runs the checks. Close the app window and double-click `3_run_app.bat`; your use case is live. |
| 11:30–12:55 | Deliverables + evidence | Everyone | `next phase` → **Phase 3**: Kilo writes `DELIVERABLES.md` using the eval numbers. Each hat corrects its own section. |
| 12:55–1:30 | Checkpoint + lunch | Integrator | Save everything. |
| 1:30–2:00 | Real-AI evidence | POC lead | Double-click `4_run_tests_and_eval.bat` once with `LLM_PROVIDER=mock` and once with the TCS key. The difference is your D4 proof. |
| 2:00–2:35 | Independent review | Integrator + 1 | **Prompt 2** in a *different* AI tool → fix gaps with **Prompt 3**. |
| 2:35–4:00 | Build slides, rehearse, record a backup video, Q&A practice | All | **Pitch & Demo Kit** in `DELIVERABLES.md` (9-slide template, script, demo clicks, Q&A bank) + **Prompt 4**. |

If something breaks, tell Kilo: *"`2_check_setup.bat` / `pytest -q` fails with: <paste error>. Fix it following the project rules."*

### Capability catalog: what is built in, and what can be added
Use this table with **Prompt 0**. **Built-in** means zero coding: you only set it in `.env` or `usecase.yaml`. **Add-on** means Kilo adds it as a small, optional module behind a `.env` switch, so the built-in path keeps working.

| Need | Built-in (zero code) | Add-on if the use case really needs it (approx. effort with Kilo) |
|---|---|---|
| UI | Streamlit: dashboard, upload, review/approve, chat, admin | Angular/React front end on the existing REST API (`api.py`) (60+ min, usually not worth it) |
| LLM / model switch | LangChain ChatOpenAI / AzureChatOpenAI: TCS gateway, OpenAI, Azure, Gemini, Ollama; fast/strong router | — |
| Orchestration / agents | LangGraph: extract ↔ validate repair loop → verify → guards, fallback | Extra LangGraph nodes, e.g. tool-calling agent, LLM reviewer node, human-approval interrupt (20–40 min) |
| Structured output | YAML-defined fields + sections, Pydantic validation, evidence per item | — |
| Chunking / large docs | LangChain RecursiveCharacterTextSplitter, parallel map-reduce | Token-based splitter (tiktoken) (10 min) |
| Caching | LangChain LLM cache (SQLite) | Semantic cache: similar questions reuse answers (20 min) |
| Retrieval / RAG | Hybrid BM25 + embeddings in SQLite via a LangChain retriever, citations | **ChromaDB** (`langchain-chroma`) or **FAISS** (`faiss-cpu`) vector store; reranker (15–25 min) |
| Documents | txt, md, docx (+tables), digital PDF, Teams/Zoom VTT | Excel/CSV ingestion (`pandas`) (10 min); HTML/email .eml (15 min) |
| Multimodal | Scanned PDF + images → vision model; audio → Whisper | Local OCR without an LLM (`rapidocr`) (20 min) |
| Guardrails / security | PII masking in and out, prompt-injection scan, blocked terms, size limit, RBAC login, audit, token budget | Presidio NER-based PII (20 min); LLM-based moderation node (15 min) |
| Classic ML / numbers | — | scikit-learn classifier or anomaly detection; forecasting (`statsmodels`) on CSV (30–45 min, new page) |
| Integrations | Jira CSV, Word, PDF, email draft, JSON, REST API | Live Jira / ServiceNow / Teams webhook calls (20–30 min each; demo with a mock endpoint) |
| Data store | SQLite (one DB per use case) | PostgreSQL / Azure SQL via `DB_URL` (30 min) |
| Observability / cost | Admin page: tokens, cost, latency, cache hits, errors, feedback, graph diagram | LangSmith / OpenTelemetry tracing (15 min, needs internet access) |
| Evaluation | gold.json + held-out sample, recall / owner / field accuracy | LLM-as-judge scoring for free-text quality (20 min) |
| Deployment | Docker, docker-compose, GitHub Actions CI | AKS / App Service manifests (slides only for the hackathon) |

### Prompt 0 — Tech-stack selector (run FIRST, before Prompt 1)
Paste it into Kilo, or into a reasoning model (AI Genie / ChatGPT / Claude). Its output feeds D2 and D3 directly.
```text
You are a pragmatic enterprise GenAI architect advising a 5-person hackathon team with a 5-hour limit
(POC build budget ~75 minutes). Read README.md (section "Capability catalog") and
.kilocode/rules/project-rules.md to understand what our template already provides.

OUR PROBLEM STATEMENT:
<<PASTE THE FULL PROBLEM STATEMENT>>

Constraints: we have a TCS-provided LLM API key (<<OpenAI-compatible / Azure — fill in>>,
embedding model available: <<yes/no>>, vision model available: <<yes/no>>). Synthetic data only. Windows laptops.

Do this:
1. FIT: Does the core of this problem match "input -> structured extraction -> human review -> chat/export"?
   Answer FITS / PARTLY FITS / DOES NOT FIT, with the reason.
2. STACK TABLE, one row per layer (UI, ingestion/modality, chunking, LLM + routing, orchestration/agents,
   structured output, retrieval/vector store, caching, guardrails/security, data store, integrations,
   evaluation, observability, deployment): chosen option | BUILT-IN or ADD-ON | why for THIS use case |
   trade-off accepted.
   Rule: prefer BUILT-IN. Choose an ADD-ON only if the problem statement or jury criteria clearly need it.
3. ADD-ONS: for each ADD-ON give the package, the files to add (new module + .env switch, never breaking
   the built-in path), effort in minutes, and whether it is needed for the DEMO or only for the ROADMAP slide.
   The total demo add-on effort must stay under 45 minutes; otherwise move items to the roadmap.
4. D2 SEEDS: 3 genuinely different architecture options for this use case (e.g. rules/classic ML vs managed
   GenAI with RAG + agents vs self-hosted open model vs buy a SaaS product), 6 weighted criteria tied to the
   success measures, scores 1-5 with reasons, weighted totals (check the arithmetic), and the pass/fail gate.
5. RISKS: top 5 technical risks of the chosen stack with mitigations.
6. A one-paragraph stack justification we can say to the jury in 30 seconds.
Do not write code in this step.
```
After the team agrees the stack, run **Prompt 1**. If Prompt 0 chose add-ons, tell Kilo in Phase 2:
*"Also implement these approved add-ons from the stack decision: <<list>>. Each one goes behind a .env switch, has a test, and must not break the other use cases."*

### Prompt 1 — MASTER (paste into Kilo, replace `<< >>`)
```text
Follow the project rules in .kilocode/rules/project-rules.md.

# CONTEXT
We are a 5-person team at TCS AI Friday (5-hour enterprise GenAI hackathon). Jury marks:
problem & success measures 15 | architecture options & decision 25 | target-state architecture 20 |
POC/validation 20 | roadmap, risks & practical GenAI 15 | presentation 5.
This repo is a tested, config-driven accelerator (LangChain + LangGraph + Streamlit). A new use case =
a new folder usecases/<name>/ with usecase.yaml + samples/*.txt + gold.json. Python code must NOT change.
Examples to copy patterns from: usecases/meeting_notes (dialogue), usecases/incident_triage (tickets),
usecases/contract_review (long documents). Every YAML key is explained in usecases/_template/usecase.yaml.

# OUR PROBLEM STATEMENT (verbatim)
<<PASTE THE FULL PROBLEM STATEMENT, DATA CONSIDERATIONS AND SOLUTION EXPECTATIONS>>

# ROLE
Senior GenAI solution architect and engineer who ships demo-safe enterprise solutions.

# ASK — work in phases. STOP after each phase and wait for me to type "next phase".
PHASE 1 (no files): reply with (a) problem in one sentence, users/stakeholders, 3-5 assumptions with the
riskiest marked, 4-6 success measures with numeric targets; (b) snake_case use-case name; (c) the design:
app labels, 1-3 classification fields with options, 2-5 sections (key, label, description, has_owner,
has_deadline, which one is_task, attributes); (d) the 4 synthetic samples you will write;
(e) FIT CHECK: does this problem fit the pattern "input -> structured extraction -> review -> chat/export"?
If part of it does not fit (e.g. forecasting on numbers, recommendations, generating content), say exactly
which part, and propose the smallest generic code addition — do not start it until I approve.
PHASE 2 (build): run `python scripts/new_usecase.py <name>`; fill usecases/<name>/usecase.yaml
(domain-specific ai.role/task/rules, realistic offline keywords, guardrails, chat examples); delete
samples/example.txt; write 4 synthetic samples (one file name containing "heldout" with messy informal
language, one with an email/phone number, one with a prompt-injection line); write gold.json (every
keyword must literally appear in its sample). Then run `python scripts/check_setup.py`, `pytest -q`,
`python -m eval.run_eval` and fix every failure. Finish with the exact steps to see it in the browser.
PHASE 3 (deliverables): rewrite DELIVERABLES.md for OUR use case, keeping every heading. Fill every <<placeholder>> in the
Pitch & Demo Kit (slide table, word-for-word script, demo click script, 3-min cut, elevator pitch, Q&A bank) with
our real names, numbers and demo sample. D1 numeric
success measures; D2 at least 3 genuinely different options, weighted criteria with correct arithmetic,
a pass/fail gate, rationale and consequences; D3 mermaid diagram consistent with D2 naming real repo
components (LangGraph pipeline, LangChain gateway/retriever, guardrails, vision ingestion); D4 uses the
numbers from usecases/<name>/eval_report_*.md and separates validated vs still-assumed; D5 phased
roadmap, dependencies, risks mapped to D3 controls; pitch script; AI usage log. Fictional but plausible
figures, consistent across sections.
PHASE 4 (only if needed): domain prompt tweaks in usecases/<name>/prompts/extract_v1.md (copy
prompts/extract_v1.md first, keep the {placeholders}). No Python changes unless I approve.

# FORMAT
Edit files directly, complete content, no TODOs. After each phase: files changed, commands run with
results, and what I should check.

# CONSTRAINTS
Synthetic data only. No secrets in files. LLM_PROVIDER=mock must still work offline. Do not create new
markdown files. If the problem statement is ambiguous, state your assumption explicitly.
```

### Prompt 2 — Independent reviewer (use a DIFFERENT AI tool or model)
```text
You are an independent reviewer for an enterprise architecture hackathon. Review first, do NOT rewrite.
Inputs: DELIVERABLES.md, usecases/<<name>>/usecase.yaml, usecases/<<name>>/eval_report_*.md, problem statement.
Score 0-10 with evidence: Coverage 25%, Completeness 20%, Cross-deliverable consistency 15%,
Evidence & traceability 15%, Business & technical quality 15%, Clarity & decision readiness 10%.
Gap register table: Gap ID | Section | Finding | Severity | Evidence | Recommended action.
Check: D1 targets numeric; D2 has ≥2 genuinely different options with fair trade-offs and correct maths;
D3 matches D2; D4 uses real eval numbers and separates validated vs assumed; D5 risks map to D3 controls.
End with the weighted readiness score /100 and the top 3 fixes.
```

### Prompt 3 — Fix the review gaps
```text
Reviewer gap register: <<PASTE>>. Fix all Critical and High gaps in DELIVERABLES.md (and the use-case folder
if needed), keep everything consistent, rerun `python -m eval.run_eval` if samples changed, and add a QA log
(score before/after, what changed) to the AI usage log section.
```

### Prompt 4 — Jury Q&A practice
```text
Act as a tough TCS jury (CTO, CISO, delivery head). Read DELIVERABLES.md and the problem statement. Ask me 10
hard questions one at a time: trade-offs, security, cost, scale, accuracy evidence, and "what if a constraint
changes" (no external LLM, 10x volume, Hindi audio). After each answer rate it 1-5 and give a sharper 2-line answer.
```

### Prompt 5 — Architecture options (reasoning model)
```text
Problem: <<...>> Constraints: <<...>> Success measures: <<...>>
Propose 3 genuinely different architectures (e.g. rules/classic ML, managed GenAI with RAG + agents,
self-hosted/fine-tuned open model, or buy a product). For each: components, data flow, pros, cons, cost
drivers, security posture, time-to-value. Give 6 weighted criteria tied to the success measures, score
1-5 with one-line reasons, compute weighted totals, name the pass/fail gate, then argue AGAINST the
winner so we can defend it.
```

### Prompt 6 — Turn the Pitch & Demo Kit into slides (any AI tool that makes decks)
```text
Create a 9-slide presentation (plus backup slides) from the "Pitch & Demo Kit" section of the DELIVERABLES.md
below. Follow its slide table exactly: claim-style titles, max 3 bullets, one big number or diagram per slide,
speaker notes = the word-for-word script for that slide. Slide 5 = the architecture diagram from D3.
Slide 7 = the eval table from D4. Two colours, clean corporate style, no stock clip-art.
<<PASTE DELIVERABLES.md>>
```

### Jury changes a constraint mid-way?
Tell Kilo: *"Jury changed constraint: <<e.g. data cannot leave India / no external LLM>>. Handle it with minimal change (prefer .env: e.g. LLM_PROVIDER=ollama or another region/endpoint). Update D2 scores, D3, D5 risks and the pitch in DELIVERABLES.md. List what changed."*

---

## Part 5 — Demo-day checklist
- [ ] `2_check_setup.bat` says **ALL GOOD** on the demo laptop *and* the demo network
- [ ] `4_run_tests_and_eval.bat` passes (tests cover every use-case folder)
- [ ] Dashboard shows data (samples load automatically on start)
- [ ] A backup screen recording of the full flow is on the desktop (`Win + G` to record)
- [ ] If AI or Wi-Fi fails live: set `LLM_PROVIDER=mock` in `.env`, restart `3_run_app.bat` (30 s), and say honestly: "this is our offline fallback"
- [ ] Each person knows their pitch part. The AI usage log has one place AI helped and one place you overruled it

---

## Part 6 — Troubleshooting
| Problem | Fix |
|---|---|
| `python` not recognized | Part 1 Step 1 again; tick *Add to PATH*; reopen the window |
| `1_setup.bat` install fails | Use a mobile hotspot, or in cmd: `pip install -r requirements.txt --proxy http://PROXY:PORT` |
| Check: `401` / auth | Wrong or expired key; copy it again without spaces |
| Check: `404` / not found | Wrong model name. Azure: use the **deployment** name, and `LLM_BASE_URL` must end with `.openai.azure.com/`. TCS gateway: check that the URL includes `/v1` if they gave you one |
| Check: `429` | Rate limit or quota: wait a minute; lower `MAX_PARALLEL=2` for big documents |
| `Connection error` / SSL error | Office network or proxy: try a hotspot, or set `LLM_CA_BUNDLE` |
| Gateway rejects `response_format` | Nothing to do; the app automatically retries without JSON mode |
| Sidebar shows 🟡 `mock` | `.env` not saved, `LLM_PROVIDER` still `mock`, or the app was not restarted |
| Items marked 🔶 *needs review* | That's the verifier working: the AI said something not found in the source. Fix it in Review, and show it to the jury |
| "Use case could not be loaded" | YAML formatting error. Run `2_check_setup.bat`, or tell Kilo: "fix usecase.yaml so check_setup passes" |
| Image / scanned PDF error | Needs a real provider + `VISION_MODEL` (a multimodal model) |
| Audio error | Needs `LLM_PROVIDER=openai/azure` + `STT_MODEL` (Whisper), or upload a transcript |
| Port 8501 busy | Close the other app window, or run `streamlit run app.py --server.port 8502` |

---

## Part 7 — Reference

### Double-click files (Windows)
| File | Does |
|---|---|
| `1_setup.bat` | one-time install (creates `.venv`, installs packages, creates `.env`) |
| `2_check_setup.bat` | checks everything + tests the API key |
| `3_run_app.bat` | loads sample data (first time) and opens the app |
| `4_run_tests_and_eval.bat` | runs all tests (every use case) + accuracy report |
macOS/Linux: `./setup.sh`, then `./run.sh`.

### Same things by hand (VS Code → Terminal → New Terminal)
```powershell
.venv\Scripts\activate                  # first, in every new terminal
python scripts\check_setup.py           # check setup + API key
python scripts\new_usecase.py my_case   # create usecases\my_case from the template and switch .env to it
python scripts\seed_samples.py --force  # (re)load sample data
streamlit run app.py                    # start the UI
pytest -q                               # tests: every use-case folder end-to-end
python -m eval.run_eval                 # accuracy report -> usecases\<name>\eval_report_<provider>.md
uvicorn api:app --reload                # optional REST API, docs at http://localhost:8000/docs
```

### `.env` settings
| Setting | Meaning |
|---|---|
| `USECASE` | which folder in `usecases/` to run |
| `LLM_PROVIDER` | `openai` (also any OpenAI-compatible gateway) · `azure` · `gemini` · `ollama` · `mock` |
| `LLM_API_KEY`, `LLM_BASE_URL` | key and endpoint |
| `LLM_MODEL_FAST`, `LLM_MODEL_STRONG` | router: cheap model for most calls, strong model for long inputs (`ROUTER_THRESHOLD_CHARS`) |
| `EMBED_MODEL` | embeddings for semantic search (blank = keyword search only) |
| `VISION_MODEL`, `STT_MODEL` | images/scanned PDFs, audio |
| `LLM_EXTRA_HEADERS`, `LLM_CA_BUNDLE` | enterprise gateway headers and certificate |
| `MAX_CHARS_PER_CALL`, `MAX_PARALLEL` | chunk size for large documents, parallel chunk calls |
| `FALLBACK_TO_MOCK` | use the offline engine if the AI fails (keep `true` for demos) |
| `DAILY_TOKEN_BUDGET`, `PRICE_IN_PER_1K`, `PRICE_OUT_PER_1K` | cost control and cost dashboard |
| `USE_LANGGRAPH` | `true` = LangGraph orchestration (default), `false` = plain Python, same result |
| `AUTH_ENABLED`, `APP_USERS` | login with roles viewer/editor/admin (`user:password:role,...`) |
| `MASK_PII_DEFAULT` | PII masking toggle default |

### Folder map
```
usecases/<name>/      usecase.yaml · samples/*.txt · gold.json   ← the ONLY part that changes per use case
  meeting_notes/ incident_triage/ contract_review/   (examples)   _template/  (starting point)
DELIVERABLES.md       jury deliverables D1–D5 + pitch + AI usage log
app.py, pages/        UI (labels come from the YAML)
core/                 llm (LangChain gateway) · guardrails · usecase loader · schemas · db · offline engine
services/             graph (LangGraph) · extractor · rag · ingest (multimodal) · exporter · pipeline · cleaner
prompts/              generic prompt templates
eval/ tests/ scripts/ api.py Dockerfile docker-compose.yml .github/workflows/ci.yml
.kilocode/rules/      rules Kilo Code follows automatically
```

### What's tested, and what isn't
- **Tested:** 17 automated tests, including the full flow for **every** use-case folder, and the LangChain + LangGraph path against a fake OpenAI-compatible server: cache, router, JSON repair loop, fallback, scanned-PDF and image vision, large-document map-reduce, and output guardrails. All UI pages were smoke-tested for all 4 folders.
- **Not tested with the real TCS endpoint:** run `2_check_setup.bat` to verify that yourself.
- **Limitations:** the offline engine is keyword-based and over-fitted to the example samples. It scores low on held-out samples by design, and that gap is your evidence for using the LLM. Jira is a CSV import, auth uses local users, and SQLite stands in for an enterprise DB / Azure AI Search.
