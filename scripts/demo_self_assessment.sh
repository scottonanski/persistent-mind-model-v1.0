#!/usr/bin/env bash
set -euo pipefail

DB_PATH="${1:-.data/pmm.db}"

echo "[*] Snapshotting events…" >&2
TMP_JSON=$(mktemp)
python -m pmm.api.probe snapshot --db "$DB_PATH" --limit 5000 > "$TMP_JSON"

echo "\n=== Last self_assessment ==="
jq -r '(.events | map(select(.kind=="self_assessment")) | last) // "(none)"' "$TMP_JSON"

echo "\n=== Last policy_update (source=self_assessment) ==="
jq -r '(.events | map(select(.kind=="policy_update" and (.meta.source // "") == "self_assessment")) | last) // "(none)"' "$TMP_JSON"

echo "\n=== Rotation history (assessment_policy_update) ==="
jq -r '(.events | map(select(.kind=="assessment_policy_update")) | .[]) // empty' "$TMP_JSON"

rm -f "$TMP_JSON"
