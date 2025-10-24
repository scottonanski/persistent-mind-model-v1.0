# Event Kinds and Examples

All events share shape `{ id:int, ts:str, kind:str, content:str, meta:dict }`. Below are representative kinds used by PMM with example payloads. See invariants in `pmm/runtime/invariants.py:1`.

## Identity

- identity_adopt
```json
{ "kind": "identity_adopt", "content": "Echo", "meta": { "name": "Echo", "sanitized": "Echo", "confidence": 0.95 } }
```
- identity_change
```json
{ "kind": "identity_change", "content": "Switching to 'Echo'" }
```
- identity_clear
```json
{ "kind": "identity_clear", "content": "" }
```

## Traits

- trait_update (single)
```json
{ "kind": "trait_update", "meta": { "trait": "conscientiousness", "delta": 0.03, "reason": "commitment_followthrough", "tick": 102 } }
```
- trait_update (multi)
```json
{ "kind": "trait_update", "meta": { "delta": { "o": 0.01, "c": 0.02, "n": -0.01 }, "reason": "evolution_kernel", "tick": 145 } }
```

## Commitments

- commitment_open
```json
{ "kind": "commitment_open", "content": "Commitment opened: Write test for snapshot delta replay", "meta": { "cid": "c9f2b5...", "text": "Write test for snapshot delta replay", "source": "assistant", "project_id": "snapshot-delta" } }
```
- evidence_candidate
```json
{ "kind": "evidence_candidate", "meta": { "cid": "c9f2b5...", "evidence_type": "done", "snippet": "Added pytest for snapshot delta" } }
```
- commitment_close
```json
{ "kind": "commitment_close", "content": "Commitment closed: c9f2b5...", "meta": { "cid": "c9f2b5...", "evidence_type": "done", "description": "PR merged", "project_id": "snapshot-delta" } }
```
- commitment_expire
```json
{ "kind": "commitment_expire", "meta": { "cid": "c9f2b5...", "reason": "ttl" } }
```
- project_open / project_assign / project_close
```json
{ "kind": "project_open", "content": "Project: snapshot-delta", "meta": { "project_id": "snapshot-delta" } }
{ "kind": "project_assign", "meta": { "cid": "c9f2b5...", "project_id": "snapshot-delta" } }
{ "kind": "project_close", "content": "Project: snapshot-delta", "meta": { "project_id": "snapshot-delta" } }
```

## Cognition

- reflection
```json
{ "kind": "reflection", "content": "Reflecting on current state: IAS=0.42, GAS=0.31...", "meta": { "source": "evolution_kernel" } }
```
- meta_reflection_report
```json
{ "kind": "meta_reflection_report", "content": "meta_analysis", "meta": { "window": "last_50", "digest": "...", "anomalies": ["shallow_reflection_pattern:0.62"] } }
```
- insight_ready (consumed once by a response)
```json
{ "kind": "insight_ready", "meta": { "from_event": 1234, "summary": "Open tests for commitment due" } }
```

## Metrics & Stage

- metrics_update
```json
{ "kind": "metrics_update", "meta": { "IAS": 0.48, "GAS": 0.35, "reason": "recomputed", "component": "metrics_system" } }
```
- gas_breakdown
```json
{ "kind": "gas_breakdown", "meta": { "total": 0.35, "ias": 0.48, "diagnosis": { "identity_adopts": 1 } } }
```
- autonomy_tick
```json
{ "kind": "autonomy_tick", "meta": { "telemetry": { "IAS": 0.48, "GAS": 0.35 }, "stage": "S2" } }
```
- stage_update / stage_progress
```json
{ "kind": "stage_update", "meta": { "from": "S1", "to": "S2" } }
{ "kind": "stage_progress", "meta": { "stage": "S2" } }
```

## Storage / Infra

- projection_snapshot (pointer event; compressed state lives in `snapshots` table)
```json
{ "kind": "projection_snapshot", "content": "Snapshot at event 2000 (schema v1.0)", "meta": { "snapshot_id": "snap_2000", "anchor_event_id": 2000, "schema_version": "v1.0", "checksum": "sha256:...", "storage": "snapshots_table", "snapshot_db_id": 12, "event_count": 2000 } }
```
- embedding_indexed / embedding_skipped
```json
{ "kind": "embedding_indexed", "meta": { "eid": 1337, "digest": "v:..." } }
{ "kind": "embedding_skipped", "meta": {} }
```
- scene_compact
```json
{ "kind": "scene_compact", "content": "...<=500 chars...", "meta": { "source_ids": [123,124,130], "window": { "start": 123, "end": 130 } } }
```

## Invariant Violations (optional)

- invariant_violation
```json
{ "kind": "invariant_violation", "meta": { "code": "evidence:close_without_candidate", "details": { "commitment_id": "c9f2b5..." } } }
```

