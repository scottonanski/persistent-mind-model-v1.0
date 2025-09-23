# TESTING-VERACITY.md

> **Purpose:**  
> This guide defines the reproducible tests that verify the Persistent Mind Model (PMM) *actually does what it claims to do*.  
> It ensures that contributors, auditors, or researchers can independently confirm the system’s persistence, self-evolution, and safety guarantees.

---

## 1. Setup

```bash
# Fresh virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]

# Initialize a fresh PMM database
rm -f .data/pmm.db
python -m pmm.cli.chat --init
```

Confirm DB schema:

```bash
sqlite3 .data/pmm.db ".tables"
# Expect: events, event_embeddings
```

---

## 2. Ledger Integrity

**Claim:** PMM uses a hash-chained, tamper-evident event log.

**Test:**

```bash
scripts/verify_pmm.sh
```

Checks:
- `events` table is append-only
- `prev_hash`/`hash` fields form a valid chain
- Any corruption is detected

**Expected Result:** `Chain verified: OK`

---

## 3. Identity Persistence

**Claim:** Identity is consistent across sessions and rebuilt from ledger.

**Test:**

1. Start a session, adopt an identity:

   ```text
   > Call me Echo.
   ```

2. End session, restart with fresh process:

   ```bash
   python -m pmm.cli.chat
   ```

3. Verify identity:

   ```sql
   sqlite3 .data/pmm.db "SELECT kind, meta FROM events WHERE kind='identity_adopt' ORDER BY id DESC LIMIT 1;"
   ```

**Expected Result:** Last identity matches "Echo".  
**And:** `build_identity()` reconstructs with correct OCEAN traits.

---

## 4. Trait Evolution

**Claim:** Traits evolve deterministically based on conversations and LLM suggestions.

**Tests:**

- **Heuristic Updates:**  
  Run a few prompts and query:

  ```sql
  SELECT id, ts, meta FROM events
  WHERE kind='trait_update'
  ORDER BY id DESC LIMIT 5;
  ```

  **Expect:** Reasons like `"novelty_push"`, `"stable_period"`, `"ratchet"`.

- **LLM Suggestions:**  
  Enable adjuster:

  ```bash
  export PMM_LLM_TRAIT_ADJUSTMENTS=1
  ```

  Prompt:

  ```text
  > You should increase your openness by 0.02 because this was creative.
  ```

  Query DB:

  ```sql
  SELECT meta FROM events
  WHERE kind='trait_update'
  ORDER BY id DESC LIMIT 1;
  ```

  **Expect:**  
  `"reason": "llm_suggestion"`, delta applied, confidence ≥ 0.6.

---

## 5. Reflection & Self-Evolution

**Claim:** PMM runs autonomous reflection cycles with self-assessment.

**Test:**

```bash
python -m pmm.cli.chat
# Let it run for ~2 minutes
```

Query DB:

```sql
SELECT id, kind, substr(content,1,120) FROM events
WHERE kind='reflection'
ORDER BY id DESC LIMIT 3;
```

**Expect:** Reflection events analyzing IAS/GAS and proposing system-level adjustments.  
Also check for `"meta_reflection"` and `"self_assessment"` events after extended runtime.

---

## 6. Commitment Lifecycle

**Claim:** PMM tracks commitments with open → evidence → close lifecycle.

**Test:**

```text
> I will write documentation.
> Done: write documentation
```

Query DB:

```sql
SELECT id, kind, meta FROM events
WHERE kind LIKE 'commitment%'
ORDER BY id DESC LIMIT 5;
```

**Expect:**  
- `commitment_open`  
- `commitment_close` (with reason: `"evidence_detected"`)  

---

## 7. End-to-End Invariant Check

**Claim:** All subsystems function together without drift.

**Test:**

```bash
pytest -q
```

and

```bash
scripts/verify_pmm.sh
```

**Expect:** All tests pass. Ledger integrity confirmed. No invariant violations.

---

## 8. Criteria for Veracity

PMM is considered working as claimed if:
- Ledger chain verifies without corruption
- Identity persists across restarts
- Traits evolve with both heuristic and LLM-driven updates
- Reflection events propose policy changes
- Commitments open and close correctly
- All tests + invariant scripts pass

---

## 9. Notes

- Fail-open design: if a subsystem breaks, the runtime continues without silent failures.  
- All events must be visible in the ledger (`events` table).  
- No hidden state: if it doesn’t appear in the DB, it didn’t happen.

---

✅ **If all checks succeed, PMM is operating as a persistent, self-evolving AI mind with verifiable behavior.**