#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${HOME}/projects/forge"
if [ ! -d "$REPO_DIR" ]; then
  git clone https://github.com/frmoded/forge.git "$REPO_DIR"
fi
cd "$REPO_DIR"

python3 -m venv .venv
source .venv/bin/activate
pip install -e .

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "ERROR: set ANTHROPIC_API_KEY before running"
  exit 1
fi

uvicorn forge.api.server:app --reload --port 8000