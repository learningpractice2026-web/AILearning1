#!/usr/bin/env bash
cd "$(dirname "$0")"
source .venv/bin/activate
python scripts/check_setup.py || true
python scripts/seed_samples.py
streamlit run app.py
