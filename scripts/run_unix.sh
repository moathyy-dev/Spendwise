#!/usr/bin/env bash
# تشغيل SpendWise على macOS أو Linux (بعد إعداده مسبقًا عبر setup_unix.sh).
set -e

cd "$(dirname "$0")/.."
source .venv/bin/activate
streamlit run app.py
