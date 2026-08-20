# PMM Reflection Reinterpretation v1 Policy Contract

- **Policy baseline:** `5a0dbef860552e274829581d355ef08782768d9a`
- **Status:** Authorized, implemented, and lifecycle-verified
- **Scope:** One exact authoritative commitment outcome review and zero or more
  later reinterpretations of that review
- **Non-goals:** General R02 governance, arbitrary reflection targets,
  reinterpretation of reinterpretations, semantic adjudication, or promotion
  into identity, policy, commitment state, adaptive learning, Mirror, or RSM

## Governing boundary

> A later reinterpretation does not rewrite a prior review. It records one new,
> explicitly related interpretation of that exact authoritative review.

The relationship is structural. It proves the exact target, ordering, and
managed producer provenance required by this contract. It does not prove that
the reinterpretation is true or semantically warranted.

## Implemented v1 contract

A v1 reinterpretation is a canonical `reflection` with protocol
`reflection_reinterpretation.v1`. Its content contains only a non-empty
`reinterpretation`. Its metadata contains exactly `protocol`, `source`, `cid`,
`open_event_id`, `outcome_event_id`, `review_event_id`, and `origin_event_id`.

Validation establishes that:

1. `review_event_id` identifies an earlier registered and still-valid
   `commitment_outcome_review.v1`;
2. the recorded CID, open event, and outcome event exactly match that review;
3. `review_event_id < origin_event_id < reinterpretation_event_id`; and
4. `origin_event_id` identifies the managed assistant that emitted the exact
   structured candidate.

The authorized candidate form is:

```text
REFLECTION_REINTERPRETATION:{"cid":"...","open_event_id":<id>,"outcome_event_id":<id>,"review_event_id":<id>,"reinterpretation":"..."}
```

An ordinary reflection, a raw protocol-shaped row, a review-like text match,
or another reinterpretation is not an eligible target. Shared CID, chronology,
`about_event`, and semantic similarity never substitute for the exact
authoritative review.

Each canonical reinterpretation projects exactly one MemeGraph `reinterprets`
edge to its recorded review. Multiple distinct later assistant candidates may
reinterpret the same review. Reprocessing the same origin, review, and canonical
content converges on the existing event.

Invalid attempts create no authoritative reinterpretation or graph edge. The
assistant utterance remains source history when present, and one typed,
digest-keyed `validation_failure` durably preserves each distinct failed
attempt. Public protocol-shaped appends route through the same boundary and
raise only after that failure record commits.

There is no migration or inference. Legacy and ordinary reflections retain
their existing behavior and cannot acquire v1 reinterpretation authority.

## Projection, retrieval, and isolation

MemeGraph is the only new structural authority. A validated reinterpretation is
attached to the same exact commitment episode through:

```text
commitment_open <- outcome_for - outcome <- reviews_outcome - review
                                                       ^
                                                       |
                                                  reinterprets
                                                       |
                                               reinterpretation
```

Episode-aware retrieval includes it only through the existing exact-episode
selection path and records CID, open ID, outcome ID, review ID,
reinterpretation ID, relationship role, and episode trigger IDs. Rebuild and
incremental graph construction must yield the same episode and retrieval result.

Protocol-shaped reviews and reinterpretations are excluded from Mirror aging
and reflection counts, RSM observation, identity summaries, stability and
meta-reflection counts, learning-pattern detection, and autonomy reflection
metrics. They do not close commitments, revise identity, mutate policy, or
enter legacy outcome adaptation.

## Falsifiable guarantee

> On every governed EventLog path, a `reflection_reinterpretation.v1` may become
> canonical and project one `reinterprets` relationship only when an authorized
> managed-assistant candidate identifies one exact earlier authoritative
> `commitment_outcome_review.v1` with matching episode lineage. Otherwise the
> relationship is not appended or projected and the failed attempt is durably
> preserved. No relationship is inferred from ordinary or legacy reflection,
> `about_event`, chronology, CID, similarity, or another reinterpretation.

The guarantee is falsified if any governed path:

- promotes a missing, ordinary, raw, wrong-episode, or recursive target;
- accepts forged managed-terminal metadata as producer proof;
- projects zero or more than one `reinterprets` edge for an authoritative event;
- collapses two genuinely later candidates into one event or duplicates exact
  reprocessing;
- drops an invalid attempt without durable failure; or
- changes Mirror, RSM, identity, commitment, adaptive-learning, or policy state.
