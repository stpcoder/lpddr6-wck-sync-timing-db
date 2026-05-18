#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$(command -v /opt/homebrew/bin/python3 || command -v python3)}"

cd "$ROOT"
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -m py_compile \
  tools/evaluate_lpddr6_timing_seed.py \
  tools/inspect_lpddr6_graph.py \
  tools/query_lpddr6_semantic_db.py \
  tools/semantic_query.py \
  tools/semantic_ui_server.py \
  tools/validate_wck_sync_timing_cases.py \
  ui/streamlit_app.py

PYTHONDONTWRITEBYTECODE=1 "$PYTHON" tools/validate_wck_sync_timing_cases.py --scope wr_rd_full
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" tools/validate_wck_sync_timing_cases.py --scope matrix_baseline
