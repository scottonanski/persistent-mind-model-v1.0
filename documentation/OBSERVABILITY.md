# Observability Guide

Make internal correctness externally obvious. This guide lists practical views, queries, and metrics to surface in the UI/API for fast health assessment.

## High-Signal Summaries
- Commitment system: `✅/⚠️/❌` with counts
  - Open now; opened/closed/expired this session
  - Extraction rate: `accepted / candidates` (expected 5–10%)
  - Avg lifespan (events) of closed commitments
- IAS/GAS trend: last N ticks + current stage (with hysteresis note)
- Reflection hygiene: acceptance rate, n-gram duplicate rate, policy-loop flags

## Recommended API Additions (non-breaking)
- Extend `/metrics?detailed=true` payload with:
  - `commitments: { open_now, opened_session, closed_session, expired_session, extraction_rate, avg_lifespan_events }`
  - `reflections: { accepted, rejected, duplicates, policy_loops }`
- Add `/commitments?status=open` (already supported) + project grouping in meta

## SQL Snippets (via `/events/sql`)
- Last 10 commitment events
```
SELECT id, ts, kind, json_extract(meta,'$.cid') AS cid,
       json_extract(meta,'$.project_id') AS project
FROM events WHERE kind LIKE 'commitment_%'
ORDER BY id DESC LIMIT 10;
```
- Evidence before close sanity check
```
SELECT c.id AS close_id, c.meta
FROM events c
LEFT JOIN events e
  ON e.kind='evidence_candidate'
 AND json_extract(e.meta,'$.cid')=json_extract(c.meta,'$.cid')
 AND e.id BETWEEN (
   SELECT MAX(id) FROM events o
   WHERE o.kind='commitment_open'
     AND json_extract(o.meta,'$.cid')=json_extract(c.meta,'$.cid')
 ) AND c.id
WHERE c.kind='commitment_close' AND e.id IS NULL
ORDER BY c.id DESC LIMIT 20;
```

## UI Hints
- Replace “Open commitments: X” with:
  - `Active: X (closed this session: Y, expired: Z, extraction 5.8%)`
- Show stage ladder with hysteresis explanation (“requires margin before changing”)
- Add tooltips linking to `documentation/INVARIANTS.md` for invariant-driven errors

## Troubleshooting Checklist
- Hash chain: run `verify_chain()` or query `/events/sql` and compare `prev_hash/hash`
- Snapshot drift: rebuild snapshot at last anchor; if mismatch, fall back to full replay
- Zero IAS: check ticks since last valid `identity_adopt` and stability windows

