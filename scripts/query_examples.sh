#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$(command -v /opt/homebrew/bin/python3 || command -v python3)}"

cd "$ROOT"

PYTHONDONTWRITEBYTECODE=1 "$PYTHON" tools/query_lpddr6_semantic_db.py detail WL

PYTHONDONTWRITEBYTECODE=1 "$PYTHON" tools/query_lpddr6_semantic_db.py target tRTRRD \
  --input speed_bin=01100 \
  --input bank_relation=different_bank_different_bg \
  --input burst_length=BL24

PYTHONDONTWRITEBYTECODE=1 "$PYTHON" tools/query_lpddr6_semantic_db.py sweep \
  --current-cmd WR \
  --next-cmd RD \
  --bank-relation different_bank_different_bg \
  --burst-length BL24 \
  --match-mr1-speed-bin \
  --mr1 00001,01100 \
  --efficiency 0,1 \
  --dvfsl 0 \
  --write-link 0,1 \
  --read-link 0 \
  --outputs "RL,WL,tCK_ns,tWTR_S,tWTR_L,WR->RD min (diff BG),tRTW"
