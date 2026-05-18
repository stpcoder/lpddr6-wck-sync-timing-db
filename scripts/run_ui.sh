#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$(command -v /opt/homebrew/bin/python3 || command -v python3)}"
PORT="${PORT:-8765}"

cd "$ROOT"
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" tools/semantic_ui_server.py --port "$PORT"
