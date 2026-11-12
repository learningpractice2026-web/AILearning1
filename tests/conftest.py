import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["LLM_PROVIDER"] = "mock"
os.environ["DB_PATH"] = str(ROOT / "tests" / "_test.db")
Path(os.environ["DB_PATH"]).unlink(missing_ok=True)

from core import db  # noqa: E402

db.init_db()
