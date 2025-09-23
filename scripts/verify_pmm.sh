#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${1:-.logs}"
DB_PATH="${2:-.data/pmm.db}"
mkdir -p "$LOG_DIR"

CHAT_LOG="$LOG_DIR/verify_chat.log"
EVENTS_JSON="$LOG_DIR/events.json"
EVENTS_RUN_JSON="$LOG_DIR/events_run.json"

export PMM_AUTONOMY_INTERVAL=1  # faster background ticks during verify
echo "[*] Establishing baseline…"
# Capture baseline last id to scope checks to this run only
BASE_ID=$(python -m pmm.api.probe snapshot --db "$DB_PATH" --limit 1 \
  | jq '( .events | last | .id ) // 0')

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

# Wait for identity_adopt to appear to avoid racing the autonomy loop
echo "[*] Waiting for identity adoption…"
adopt=0
for i in {1..20}; do
  adopt=$(python -m pmm.api.probe snapshot --db "$DB_PATH" --limit 999999 \
    | jq '[.events[]|select(.kind=="identity_adopt")] | length')
  if [ "${adopt:-0}" -ge 1 ]; then
    break
  fi
  sleep 1
done
if [ "${adopt:-0}" -lt 1 ]; then
  echo "FAIL: no identity_adopt (timeout)"; exit 1;
fi

echo "[*] Exporting events snapshot…"
python -m pmm.api.probe snapshot --db "$DB_PATH" --limit 2000 > "$EVENTS_JSON"
jq --argjson base "$BASE_ID" '{ events: [ .events[] | select(.id > $base) ] }' \
  "$EVENTS_JSON" > "$EVENTS_RUN_JSON"

echo "[*] Basic presence checks with jq…"
jq -e '.events | length > 0' "$EVENTS_RUN_JSON" >/dev/null

ID_PROPOSE=$(jq '[.events[]|select(.kind=="identity_propose")] | length' "$EVENTS_RUN_JSON")
ID_ADOPT=$(jq   '[.events[]|select(.kind=="identity_adopt")]   | length' "$EVENTS_RUN_JSON")
CU_COUNT=$(jq   '[.events[]|select(.kind=="curriculum_update")] | length' "$EVENTS_RUN_JSON")
PU_COUNT=$(jq   '[.events[]|select(.kind=="policy_update")]     | length' "$EVENTS_RUN_JSON")
TRAITS=$(jq     '[.events[]|select(.kind=="trait_update")]      | length' "$EVENTS_RUN_JSON")

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
' "$EVENTS_RUN_JSON" >/dev/null || {
  echo "FAIL: CU↔PU not 1:1 by src_id (bridge-only)"; exit 1; }

echo "[*] Header & notices smoke checks…"
# sanitize: strip ANSI + carriage returns + trim leading spaces
SANITIZED="$LOG_DIR/chat_sanitized.log"
sed -r 's/\x1B\[[0-9;]*[mK]//g' "$CHAT_LOG" | tr -d '\r' | sed 's/^[[:space:]]*//' > "$SANITIZED"

grep -q "identity=.* | stage=S[0-9] | traits=" "$SANITIZED" \
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
  has_proj_commit=$(jq -r '[ .events[] | select(.kind=="commitment_open" and (.meta.project_id? != null)) ] | length // 0' "$EVENTS_RUN_JSON")
  if [ "${has_proj_commit:-0}" -gt 0 ]; then
    opens=$(jq -r '[ .events[] | select(.kind=="project_open") ] | length // 0' "$EVENTS_RUN_JSON")
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
        | length // 0 ) ] | add // 0' "$EVENTS_RUN_JSON")
  if [ "${bad:-0}" -gt 0 ]; then
    echo "FAIL: project_close emitted while children still open"; exit 1;
  fi
  echo "[*] Meta-reflection checks…"
  RC=$(jq '[.events[] | select(.kind=="reflection")] | length' "$EVENTS_RUN_JSON")
  if [ "${RC:-0}" -ge 5 ]; then
    MRC=$(jq '[.events[] | select(.kind=="meta_reflection")] | length' "$EVENTS_RUN_JSON")
    EXPECTED=$(( RC / 5 ))
    if [ "${MRC:-0}" -ne "${EXPECTED:-0}" ]; then
      echo "FAIL: meta_reflection count ($MRC) != floor(reflections/5) ($EXPECTED)"; exit 1;
    fi
    # Every meta_reflection must have window==5 and efficacy in [0,1]
    bad_meta=$(jq '[.events[]
      | select(.kind=="meta_reflection")
      | select((.meta.window // 0) != 5
               or (.meta.efficacy|tonumber < 0)
               or (.meta.efficacy|tonumber > 1))] | length' "$EVENTS_RUN_JSON")
    if [ "${bad_meta:-0}" -ne 0 ]; then
      echo "FAIL: meta_reflection has bad window or efficacy out of range"; exit 1;
    fi
    # Efficacy must equal closed / max(1, opened) (±1e-6 tolerance)
    bad_eff=$(jq '[.events[]
      | select(.kind=="meta_reflection")
      | (.meta.closed / (if (.meta.opened // 0) > 0 then .meta.opened else 1 end)) as $eff
      | select( ((.meta.efficacy - $eff) | tonumber | abs) > 0.000001 )] | length' "$EVENTS_RUN_JSON")
    if [ "${bad_eff:-0}" -ne 0 ]; then
      echo "FAIL: meta_reflection efficacy != closed/max(1,opened)"; exit 1;
    fi
  else
    echo "[meta-reflection] Skipping count checks (reflections < 5)"
  fi
  echo "[*] Self-assessment checks…"
  RC=$(jq '[.events[] | select(.kind=="reflection")] | length' "$EVENTS_RUN_JSON")
  if [ "${RC:-0}" -ge 10 ]; then
    SAC=$(jq '[.events[] | select(.kind=="self_assessment")] | length' "$EVENTS_RUN_JSON")
    SA_EXPECT=$(( RC / 10 ))
    if [ "${SAC:-0}" -ne "${SA_EXPECT:-0}" ]; then
      echo "FAIL: self_assessment count ($SAC) != floor(reflections/10) ($SA_EXPECT)"; exit 1;
    fi
    # Every self_assessment must have window==10 and efficacy in [0,1], and correct formula math
    bad_sa=$(jq '[.events[]
      | select(.kind=="self_assessment")
      | select((.meta.window // 0) != 10
               or (.meta.efficacy|tonumber < 0)
               or (.meta.efficacy|tonumber > 1)
               or (((.meta.closed / (if (.meta.opened // 0) > 0 then .meta.opened else 1 end)) - .meta.efficacy) | tonumber | abs) > 0.000001)
      ] | length' "$EVENTS_RUN_JSON")
    if [ "${bad_sa:-0}" -ne 0 ]; then
      echo "FAIL: self_assessment has bad window/efficacy"; exit 1;
    fi
    # Window integrity: start/end ids present; exactly 10 reflections in window; inputs_hash looks like sha256
    bad_win=$(jq '[.events[] | select(.kind=="self_assessment")
      | select((.meta.window_start_id? == null) or (.meta.window_end_id? == null) or (.meta.inputs_hash? == null))] | length' "$EVENTS_RUN_JSON")
    if [ "${bad_win:-0}" -ne 0 ]; then
      echo "FAIL: self_assessment missing window_start_id/window_end_id/inputs_hash"; exit 1;
    fi
    bad_span=$(jq '[.events[] as $root | select($root.kind=="self_assessment") |
      ( [ .events[] | select(.kind=="reflection" and (.id > $root.meta.window_start_id) and (.id <= $root.meta.window_end_id)) ] | length ) as $rc |
      select($rc != 10) ] | length' "$EVENTS_RUN_JSON")
    if [ "${bad_span:-0}" -ne 0 ]; then
      echo "FAIL: self_assessment window does not span exactly 10 reflections"; exit 1;
    fi
    bad_hash=$(jq '[.events[] | select(.kind=="self_assessment")
      | select((.meta.inputs_hash | type != "string") or ((.meta.inputs_hash | test("^[a-f0-9]{64}$")) | not))] | length' "$EVENTS_RUN_JSON")
    if [ "${bad_hash:-0}" -ne 0 ]; then
      echo "FAIL: self_assessment inputs_hash not present/valid"; exit 1;
    fi
    bad_actk=$(jq '[.events[] | select(.kind=="self_assessment")
      | select((.meta.actions_kind | type != "string") or (.meta.actions_kind != "commitment_open:source=reflection"))] | length' "$EVENTS_RUN_JSON")
    if [ "${bad_actk:-0}" -ne 0 ]; then
      echo "FAIL: self_assessment actions_kind missing or unexpected"; exit 1;
    fi
    # Uniqueness: each inputs_hash must be unique across self_assessment events
    dup_hash=$(jq '[.events[] | select(.kind=="self_assessment") | .meta.inputs_hash] as $h | ($h | length) as $n | ($h | unique | length) as $u | select($n != $u) | 1' "$EVENTS_RUN_JSON")
    if [ "${dup_hash:-0}" = "1" ]; then
      echo "FAIL: duplicate self_assessment inputs_hash detected (duplicate window)"; exit 1;
    fi
    # Presence of a self_assessment-driven policy_update
    SA_PU=$(jq '[.events[] | select(.kind=="policy_update" and (.meta.source // "") == "self_assessment")] | length' "$EVENTS_RUN_JSON")
    if [ "${SA_PU:-0}" -lt 1 ]; then
      echo "FAIL: missing policy_update with source=self_assessment"; exit 1;
    fi
    # Bounds and metadata on cadence policy updates
    bad_bounds=$(jq '[.events[] | select(.kind=="policy_update" and (.meta.source // "") == "self_assessment")
      | (.meta.params.min_turns // 0) as $t | (.meta.params.min_time_s // 0) as $s
      | select(($t < 1) or ($t > 6) or ($s < 10) or ($s > 300) or (.meta.prev_policy? == null) or (.meta.new_policy? == null))] | length' "$EVENTS_RUN_JSON")
    if [ "${bad_bounds:-0}" -ne 0 ]; then
      echo "FAIL: self_assessment policy_update out of bounds or missing prev/new snapshots"; exit 1;
    fi
    # Round-robin meta-assessment rotation events expected every 3 assessments
    ROT_EXP=$(( SAC / 3 ))
    ROT_ACT=$(jq '[.events[] | select(.kind=="assessment_policy_update")] | length' "$EVENTS_RUN_JSON")
    if [ "${ROT_ACT:-0}" -lt "${ROT_EXP:-0}" ]; then
      echo "FAIL: assessment_policy_update count ($ROT_ACT) < floor(self_assessment/3) ($ROT_EXP)"; exit 1;
    fi
    # Rotation index and formula alignment
    bad_rot=$(jq '[.events[] | select(.kind=="assessment_policy_update")
      | ((.meta.self_assessment_count // 3) % 3) as $idx
      | select( (.meta.rotation_index // -1) != $idx
                or ((.meta.formula=="v1" and $idx!=1) or (.meta.formula=="v2" and $idx!=2) or (.meta.formula=="v3" and $idx!=0)) )] | length' "$EVENTS_RUN_JSON")
    if [ "${bad_rot:-0}" -ne 0 ]; then
      echo "FAIL: assessment_policy_update rotation_index/formula mismatch"; exit 1;
    fi
    echo "OK: self-assessment checks passed"
  else
    echo "[self-assessment] Skipping count checks (reflections < 10)"
  fi
fi
