#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
cd backend
test -f .env || cp .env.example .env
python scripts/import_excel.py
python scripts/seed_demo.py

