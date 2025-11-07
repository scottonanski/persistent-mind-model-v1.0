#!/usr/bin/env bash
set -euo pipefail

WITH_OPENAI=0
PY_BIN="${PY_BIN:-}"

for arg in "$@"; do
  case "$arg" in
    --with-openai) WITH_OPENAI=1 ;;
    --python=*) PY_BIN="${arg#*=}" ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

# Choose Python
if [[ -z "$PY_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PY_BIN=python3
  elif command -v python >/dev/null 2>&1; then
    PY_BIN=python
  else
    echo "Python 3 is required" >&2
    exit 1
  fi
fi

echo "Using Python: $($PY_BIN -V 2>&1)"

# Create venv
if [[ ! -d .venv ]]; then
  "$PY_BIN" -m venv .venv
fi
source .venv/bin/activate

python -m pip install --upgrade pip wheel setuptools

# Install runtime deps
pip install -r requirements.txt

# Optional extras
if [[ "$WITH_OPENAI" == "1" ]]; then
  pip install "openai>=1.0.0"
fi

# Install package (console script `pmm`)
pip install -e .

echo
echo "Setup complete. Activate with: source .venv/bin/activate"
echo "Run CLI: pmm"
echo "Run tests: pip install -r requirements-dev.txt && pytest -q"

