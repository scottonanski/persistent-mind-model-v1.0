# Glossary

- EventLog: Append-only SQLite database of events with hash chaining. `pmm/storage/eventlog.py:1`
- Projection: Deterministic fold of events into current state (identity, commitments). `pmm/storage/projection.py:1`
- Snapshot: Compressed projection state anchored to a specific event id. `pmm/storage/snapshot.py:1`
- Identity: The agent’s name and traits, derived from ledger events.
- OCEAN: Personality trait vector (openness, conscientiousness, extraversion, agreeableness, neuroticism).
- Commitment: An explicit intention captured as `commitment_open` with a CID; later closed with evidence.
- Evidence: Justification for closing a commitment; represented by `evidence_candidate` and consumed by `commitment_close`.
- IAS: Identity Autonomy/Authenticity Score (identity stability over time). `pmm/runtime/metrics.py:1`
- GAS: Growth via Action Score (commitment-driven growth). `pmm/runtime/metrics.py:1`
- Stage: Development stage S0–S4 inferred from IAS/GAS windows. `pmm/runtime/stage_tracker.py:1`
- Reflection: Self-referential text entries that can produce commitments and policy changes. `pmm/runtime/reflector.py:1`
- Meta Reflection: Embedding-based semantic scoring over reflections. `pmm/runtime/meta/meta_reflection.py:1`
- MemeGraph: Optional graph projection of events and identity relations. `pmm/runtime/memegraph.py:1`
- Companion API: FastAPI endpoints for UI and integrations. `pmm/api/companion.py:1`

