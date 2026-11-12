"""Load all synthetic samples of the active use case (USECASE in .env) into its DB. Run before the demo:
    python scripts/seed_samples.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402
from core.usecase import get_usecase  # noqa: E402
from services.pipeline import process_text  # noqa: E402

db.init_db()
uc = get_usecase()
print(f"Use case: {uc.slug}  ({uc.app.name})")
if db.list_records() and "--force" not in sys.argv:
    print("Samples already loaded (use --force to load again).")
    sys.exit(0)
for f in sorted(uc.samples_dir.glob("*.txt")):
    raw = f.read_text(encoding="utf-8")
    date = next((l.split(":", 1)[1].strip() for l in raw.splitlines()[:6] if l.lower().startswith("date:")), "")
    rep = process_text(raw, record_date=date, source_name=f.name, user="seed")
    print(f"#{rep.record_id}  {rep.insights.title}  ({rep.meta.get('items_total')} items, {rep.seconds}s)")
