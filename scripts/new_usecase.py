"""Create a new use-case folder from the template and switch .env to it.
    python scripts/new_usecase.py claims_triage"""
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) != 2 or not re.fullmatch(r"[a-z][a-z0-9_]*", sys.argv[1]):
    sys.exit("Usage: python scripts/new_usecase.py <snake_case_name>   e.g. claims_triage")
name = sys.argv[1]
dst = ROOT / "usecases" / name
if dst.exists():
    sys.exit(f"usecases/{name} already exists")
shutil.copytree(ROOT / "usecases" / "_template", dst)

env = ROOT / ".env"
if not env.exists():
    shutil.copy(ROOT / ".env.example", env)
text = env.read_text(encoding="utf-8")
text = re.sub(r"^USECASE=.*$", f"USECASE={name}", text, flags=re.M) if re.search(r"^USECASE=", text, re.M) \
    else f"USECASE={name}\n" + text
env.write_text(text, encoding="utf-8")
print(f"Created usecases/{name}/ and set USECASE={name} in .env")
print("Next: ask Kilo Code to fill usecase.yaml, samples/ and gold.json (README.md, Part 4, Prompt 1).")
