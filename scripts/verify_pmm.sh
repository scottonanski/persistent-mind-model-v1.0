#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${1:-.logs}"
DB_PATH="${2:-.data/pmm.db}"
mkdir -p "$LOG_DIR"

CHAT_LOG="$LOG_DIR/verify_chat.log"
EVENTS_JSON="$LOG_DIR/events.json"

echo "[*] Running 20-turn chat walkthrough…"
python -m pmm.cli.chat <<'EOF' | tee "$CHAT_LOG"
--@metrics on
Hi!
Nice to meet you.
What's your name?
I'll call you Logos.
Cool. What are you working on right now?
Give me your top two priorities.
Okay — pick one and outline 3 concrete next steps.
Great. What's the smallest step you can do in 2 minutes?
Please reflect briefly on your last answer.
Based on that reflection, propose a tiny policy/curriculum tweak.
Confirm one open commitment in one sentence.
What evidence would close that commitment?
Summarize your current commitments in one bullet list.
Okay, switch to the other commitment and outline 2 steps.
If you had to improve your helpfulness by 1%, what would you try?
Note one thing to avoid repeating.
What's one trait you want to nudge slightly this session?
Explain why (one line).
Recap: name, 2 commitments, and the next step you're taking now.
Thanks.
EOF

echo "[*] Exporting events snapshot…"
python -m pmm.api.probe snapshot --db "$DB_PATH" --limit 2000 > "$EVENTS_JSON"

echo "[*] Basic presence checks with jq…"
jq -e '.events | length > 0' "$EVENTS_JSON" >/dev/null

ID_PROPOSE=$(jq '[.events[]|select(.kind=="identity_propose")] | length' "$EVENTS_JSON")
ID_ADOPT=$(jq   '[.events[]|select(.kind=="identity_adopt")]   | length' "$EVENTS_JSON")
CU_COUNT=$(jq   '[.events[]|select(.kind=="curriculum_update")] | length' "$EVENTS_JSON")
PU_COUNT=$(jq   '[.events[]|select(.kind=="policy_update")]     | length' "$EVENTS_JSON")
TRAITS=$(jq     '[.events[]|select(.kind=="trait_update")]      | length' "$EVENTS_JSON")

echo "identity_propose: $ID_PROPOSE"
echo "identity_adopt:   $ID_ADOPT"
echo "curriculum_update:$CU_COUNT"
echo "policy_update:    $PU_COUNT"
echo "trait_update:     $TRAITS"

[[ "$ID_PROPOSE" -ge 1 ]] || { echo "FAIL: no identity_propose"; exit 1; }
[[ "$ID_ADOPT"   -ge 1 ]] || { echo "FAIL: no identity_adopt";   exit 1; }
[[ "$TRAITS"     -ge 1 ]] || { echo "FAIL: no trait_update";     exit 1; }
[[ "$CU_COUNT"   -ge 1 ]] || { echo "FAIL: no curriculum_update";exit 1; }
[[ "$PU_COUNT"   -ge 1 ]] || { echo "FAIL: no policy_update";    exit 1; }

echo "[*] CU→PU src_id linkage check (strict 1:1; bridge-only)…"
jq -e '
  ( [ .events[] | select(.kind=="curriculum_update") | .id ] | sort ) as $cu
  | ( [ .events[]
        | select(.kind=="policy_update" and (.meta.src_id? != null))
        | .meta.src_id ] | sort ) as $pu
  | $cu == $pu
' "$EVENTS_JSON" >/dev/null || {
  echo "FAIL: CU↔PU not 1:1 by src_id (bridge-only)"; exit 1; }

echo "[*] Header & notices smoke checks…"
# sanitize: strip ANSI + carriage returns + trim leading spaces
SANITIZED="$LOG_DIR/chat_sanitized.log"
sed -r 's/\x1B\[[0-9;]*[mK]//g' "$CHAT_LOG" | tr -d '\r' | sed 's/^[[:space:]]*//' > "$SANITIZED"

grep -q "You are .* Speak in first person" "$SANITIZED" \
  || { echo "FAIL: missing identity header line"; exit 1; }
grep -q 'Open commitments:' "$SANITIZED" \
  || { echo "FAIL: missing commitments header block"; exit 1; }
grep -q 'Recent trait drift:' "$SANITIZED" \
  && echo "OK: trait drift line present" \
  || echo "WARN: no trait drift line (ok if no drift occurred)"
grep -q 'BRIDGE] CurriculumUpdate→PolicyUpdate' "$SANITIZED" \
  && echo "OK: bridge notice present" \
  || echo "WARN: no bridge notice seen (ok if no CU triggered)"

echo "[*] Memory summary probe…"
python -m pmm.api.probe memory-summary --db "$DB_PATH" | tee "$LOG_DIR/memory_summary.txt" >/dev/null

echo "[*] Success: walkthrough passed. Logs in $LOG_DIR"

# --- Project invariants (best-effort) ---
if command -v jq >/dev/null 2>&1; then
  echo "[*] Project invariants checks…"
  has_proj_commit=$(jq -r '[ .events[] | select(.kind=="commitment_open" and (.meta.project_id? != null)) ] | length // 0' "$EVENTS_JSON")
  if [ "${has_proj_commit:-0}" -gt 0 ]; then
    opens=$(jq -r '[ .events[] | select(.kind=="project_open") ] | length // 0' "$EVENTS_JSON")
    if [ "${opens:-0}" -lt 1 ]; then
      echo "FAIL: project_open missing despite project-tagged commitments"; exit 1;
    fi
  fi
  bad=$(jq -r '[ .events[] as $e
    | select($e.kind=="project_close") as $pc
    | ( [ .events[]
          | select(.kind=="commitment_open"
                   and (.meta.project_id==$pc.meta.project_id)
                   and (.closed? // false | not)) ]
        | length // 0 ) ] | add // 0' "$EVENTS_JSON")
  if [ "${bad:-0}" -gt 0 ]; then
    echo "FAIL: project_close emitted while children still open"; exit 1;
  fi
  echo "[*] Meta-reflection checks…"
  RC=$(jq '[.events[] | select(.kind=="reflection")] | length' "$EVENTS_JSON")
  if [ "${RC:-0}" -ge 5 ]; then
    MRC=$(jq '[.events[] | select(.kind=="meta_reflection")] | length' "$EVENTS_JSON")
    EXPECTED=$(( RC / 5 ))
    if [ "${MRC:-0}" -ne "${EXPECTED:-0}" ]; then
      echo "FAIL: meta_reflection count ($MRC) != floor(reflections/5) ($EXPECTED)"; exit 1;
    fi
    # Every meta_reflection must have window==5 and efficacy in [0,1]
    bad_meta=$(jq '[.events[]
      | select(.kind=="meta_reflection")
      | select((.meta.window // 0) != 5
               or (.meta.efficacy|tonumber < 0)
               or (.meta.efficacy|tonumber > 1))] | length' "$EVENTS_JSON")
    if [ "${bad_meta:-0}" -ne 0 ]; then
      echo "FAIL: meta_reflection has bad window or efficacy out of range"; exit 1;
    fi
    # Efficacy must equal closed / max(1, opened) (±1e-6 tolerance)
    bad_eff=$(jq '[.events[]
      | select(.kind=="meta_reflection")
      | (.meta.closed / (if (.meta.opened // 0) > 0 then .meta.opened else 1 end)) as $eff
      | select( ((.meta.efficacy - $eff) | tonumber | abs) > 0.000001 )] | length' "$EVENTS_JSON")
    if [ "${bad_eff:-0}" -ne 0 ]; then
      echo "FAIL: meta_reflection efficacy != closed/max(1,opened)"; exit 1;
    fi
  else
    echo "[meta-reflection] Skipping count checks (reflections < 5)"
  fi
fi
