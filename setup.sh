#!/usr/bin/env bash
# macOS / Linux one-time setup
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
echo "Setup done. Edit .env, then: ./run.sh"
