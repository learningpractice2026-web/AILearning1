"""POC evidence generator (deliverable D4) — generic, driven by usecases/<USECASE>/gold.json.

gold.json format:
{
  "<sample file name>": {
    "_note": "optional; put 'heldout' in the FILE NAME for held-out samples",
    "fields":   {"category": "Client Call"},                       # optional exact-match checks
    "<section key>": [ ["kw1", "kw2"],                                # item must contain all keywords
                       {"kw": ["kw"], "owner": "Rahul", "deadline": "Friday"} ]   # + owner/deadline checks
  }
}
Run:  LLM_PROVIDER=mock python -m eval.run_eval      (baseline)
      LLM_PROVIDER=openai python -m eval.run_eval    (real model)
Writes usecases/<USECASE>/eval_report_<provider>.md — paste it into D4."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DB_PATH", str(Path(__file__).parent / "eval.db"))

from core import db  # noqa: E402
from core.config import get_settings  # noqa: E402
from core.guardrails import PII_PATTERNS  # noqa: E402
from core.usecase import get_usecase  # noqa: E402
from services.pipeline import process_text  # noqa: E402


def _match(kws: list[str], text: str) -> bool:
    return all(k.lower() in text.lower() for k in kws)


def _pct(h: int, n: int) -> str:
    return f"{h}/{n} = {100 * h / n:.0f}%" if n else "-"


def evaluate() -> str:
    db.init_db()
    uc = get_usecase()
    gold_path = uc.dir / "gold.json"
    if not gold_path.exists():
        return f"No gold set at {gold_path}. Create one (see docstring) to get D4 evidence."
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    provider = get_settings().llm_provider
    keys = [s.key for s in uc.sections]
    groups = {g: {"sec": {k: [0, 0] for k in keys}, "own": [0, 0], "dl": [0, 0], "fld": [0, 0]}
              for g in ("dev", "heldout")}
    rows = []
    for name, exp in gold.items():
        if name.startswith("_"):
            continue
        path = uc.samples_dir / name
        if not path.exists():
            continue
        g = groups["heldout" if "heldout" in name.lower() else "dev"]
        t0 = time.perf_counter()
        rep = process_text(path.read_text(encoding="utf-8"), source_name=name, store=False)
        ins = rep.insights
        row = {"sample": name, "latency": round(time.perf_counter() - t0, 2),
               "grounding": rep.meta.get("grounding_rate"), "engine": rep.meta.get("provider")}
        for fname, fval in (exp.get("fields") or {}).items():
            g["fld"][1] += 1
            g["fld"][0] += str(ins.fields.get(fname, "")).lower() == str(fval).lower()
        for k in keys:
            got = ins.sections.get(k, [])
            hits = 0
            for e in exp.get(k, []):
                kws = e["kw"] if isinstance(e, dict) else e
                found = next((it for it in got if _match(kws, f"{it.text} {it.evidence}")), None)
                hits += bool(found)
                if isinstance(e, dict):
                    if "owner" in e:
                        g["own"][1] += 1
                        g["own"][0] += bool(found) and (found.owner or "").lower() == str(e["owner"]).lower()
                    if e.get("deadline"):
                        g["dl"][1] += 1
                        g["dl"][0] += bool(found) and e["deadline"].lower() in (found.deadline or "").lower()
            n = len(exp.get(k, []))
            g["sec"][k][0] += hits
            g["sec"][k][1] += n
            row[k] = f"{hits}/{n} (+{max(len(got) - hits, 0)})"
        row["pii"] = sum(len(p.findall(ins.model_dump_json())) for p in PII_PATTERNS.values())
        rows.append(row)

    labels = {s.key: s.label for s in uc.sections}
    lines = [f"# Eval report — use case `{uc.slug}` — engine `{provider}`", "",
             "| Sample | " + " | ".join(labels[k] for k in keys) + " | Grounding | PII leaks | Latency s |",
             "|---|" + "---|" * (len(keys) + 3)]
    for r in rows:
        lines.append(f"| {r['sample']} | " + " | ".join(r[k] for k in keys)
                     + f" | {r['grounding']} | {r['pii']} | {r['latency']} |")
    lines += ["", "(+n) = extra items not in the gold set (valid finds or noise → human precision check)", "",
              "## Aggregate", "| Metric | Dev samples | Held-out samples |", "|---|---|---|"]
    for k in keys:
        lines.append(f"| Recall — {labels[k]} | {_pct(*groups['dev']['sec'][k])} | {_pct(*groups['heldout']['sec'][k])} |")
    for key, lab in (("own", "Owner accuracy"), ("dl", "Deadline accuracy"), ("fld", "Field accuracy")):
        if groups["dev"][key][1] or groups["heldout"][key][1]:
            lines.append(f"| {lab} | {_pct(*groups['dev'][key])} | {_pct(*groups['heldout'][key])} |")
    lines += ["", "_Dev samples were visible while writing the offline rules (over-fitted). "
              "Compare engines on the held-out column._"]
    report = "\n".join(lines)
    (uc.dir / f"eval_report_{provider}.md").write_text(report, encoding="utf-8")
    return report


if __name__ == "__main__":
    print(evaluate())
