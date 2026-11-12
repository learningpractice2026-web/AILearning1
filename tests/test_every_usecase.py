"""Runs the WHOLE flow for EVERY folder in usecases/ (including any new one Kilo creates):
YAML valid -> every sample processed through the LangGraph pipeline -> items stored -> review/update ->
RAG chat -> all exports -> gold.json keywords actually exist in the samples (catches bad gold files)."""
import json

import pytest

from core import db
from core.schemas import Insights
from core.usecase import USECASES_DIR, load_usecase

FOLDERS = sorted(p.name for p in USECASES_DIR.iterdir() if (p / "usecase.yaml").exists())


@pytest.mark.parametrize("slug", FOLDERS)
def test_usecase_end_to_end(slug, monkeypatch, tmp_path):
    monkeypatch.setenv("USECASE", slug)
    s = db.get_settings()
    monkeypatch.setattr(db, "get_settings", lambda: s.__class__(**{**s.__dict__, "db_path": str(tmp_path / "x.db")}))
    db.init_db()  # fresh DB per use case

    uc = load_usecase(slug)
    assert uc.sections, "at least one section"
    assert len({x.key for x in uc.sections}) == len(uc.sections), "duplicate section keys"
    assert sum(x.is_task for x in uc.sections) <= 1, "only one section may have is_task: true"
    samples = sorted(uc.samples_dir.glob("*.txt"))
    assert samples, f"usecases/{slug}/samples/ needs at least one .txt"

    from services import exporter, rag
    from services.pipeline import process_text
    total_items = 0
    for f in samples:
        rep = process_text(f.read_text(encoding="utf-8"), source_name=f.name)
        assert rep.record_id and isinstance(rep.insights, Insights)
        assert set(rep.insights.sections) == {x.key for x in uc.sections}
        total_items += rep.meta["items_total"]
        rec = db.get_record(rep.record_id)
        db.update_insights(rep.record_id, rec["insights"], approved=True, user="test")   # review path
        ins = db.get_record(rep.record_id)["insights"]
        assert exporter.to_markdown(rec["title"], "", ins, uc)
        assert exporter.to_docx(rec["title"], "", ins, uc)[:2] == b"PK"
        assert exporter.to_pdf(rec["title"], "", ins, uc)[:4] == b"%PDF"
        assert exporter.to_jira_csv(rec["title"], ins, uc)
        assert exporter.to_email(rec["title"], "", ins, uc)
    assert total_items > 0, "offline keywords found nothing in any sample - improve section keywords"
    for q in uc.chat.examples[:2] or ["summary"]:
        assert rag.ask(q).text

    gold_path = uc.dir / "gold.json"
    if gold_path.exists():
        gold = json.loads(gold_path.read_text(encoding="utf-8"))
        for name, exp in gold.items():
            if name.startswith("_"):
                continue
            assert (uc.samples_dir / name).exists(), f"gold.json refers to missing sample {name}"
            text = (uc.samples_dir / name).read_text(encoding="utf-8").lower()
            for key, items in exp.items():
                if key in ("_note", "fields"):
                    continue
                assert key in {x.key for x in uc.sections}, f"gold.json uses unknown section '{key}'"
                for e in items:
                    for kw in (e["kw"] if isinstance(e, dict) else e):
                        assert kw.lower() in text, f"gold keyword '{kw}' not in {name}"
