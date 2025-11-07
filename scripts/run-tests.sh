#!/usr/bin/env bash
set -euo pipefail

source .venv/bin/activate 2>/dev/null || {
  echo "Virtualenv not found. Run scripts/bootstrap.sh first." >&2
  exit 1
}

pip install -r requirements-dev.txt
pytest -q

