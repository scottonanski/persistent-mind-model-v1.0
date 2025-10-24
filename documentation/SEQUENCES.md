# End-to-End Sequences

Textual sequence diagrams describe the core flows. These align with the runtime pipeline and ledger semantics.

## User Chat

```
Client -> Companion API (POST /chat)
API -> Runtime: get_or_create (model, db)
Runtime -> EventLog: read_tail (context)
Runtime -> ContextBuilder: build_context_from_ledger
Runtime -> Adapter (LLM): generate_with_budget(messages)
Adapter -> Runtime: text chunk(s)
Runtime -> NLG Guards: guard_capability_claims(text)
Runtime -> Validators: optional checks (probe/gate formats)
Runtime -> EventLog: append("response", text, meta)
Runtime -> CommitmentTracker: process_assistant_reply(text)
CommitmentTracker -> EventLog: append(commitment_open ...)*
Runtime -> Metrics: get_or_compute_ias_gas + maybe metrics_update
API -> Client: SSE frames with delta content and DONE
```

Notes:
- Commitments may open based on assistant text; evidence closes happen later.
- Additional hooks (planning thought, guidance bias, recall) may append auxiliary events.

## Autonomy Tick

```
Background Scheduler -> Runtime: tick
Runtime -> EventLog: read_tail (recent context)
Runtime -> Metrics: get_or_compute_ias_gas (may append metrics_update)
Runtime -> StageTracker: infer_stage(window)
Runtime -> Reflector: maybe_reflect(cooldown)
Reflector -> EventLog: append("reflection", ...)
Reflector -> CommitmentTracker: extract + open commitments
CommitmentTracker -> EventLog: append(commitment_open ...)*
Runtime -> EventLog: append("autonomy_tick", {telemetry: IAS,GAS, stage})
```

Notes:
- Reflection acceptance gate enforces hygiene and novelty before recording.
- Stage hysteresis avoids flapping; policy hints can be emitted around transitions.

