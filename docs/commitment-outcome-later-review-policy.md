# PMM Commitment Outcome and Later-Review Policy Contract

- **Policy baseline:** `b0f139d13f7ca360751556830168694ff4aafd8c`
- **Status:** Authorized, implemented, lifecycle-verified, and published on
  `main` in PR #22 (`e3fe3a625587732ae748b14bde4db66e17b67be5`)
- **Scope:** One exact commitment episode, at most one outcome observation, and zero or more later reviews
- **Non-goals:** Reopening R07/R08 lifecycle semantics, defining fulfillment, designing a general outcome ontology, adjudicating truth, or promoting a review into identity state

## Governing boundary

> Closing a commitment says the obligation transitioned out of open state. An
> outcome records what actually happened. A later review records what that
> outcome came to mean. These are separate acts and must not be inferred from
> one another.

For this structural contract, “records what actually happened” means that an
authorized producer records an observation with explicit provenance. It does
not mean PMM has proved the observation true or semantically adequate.

## Pre-implementation facts at the policy baseline

- A `CommitmentEpisode` is already identified by its canonical
  `commitment_open` event ID. A CID can have multiple episodes and is not an
  exact episode identity.
- A governed R08 close records the exact `open_event_id` whose state it
  transitions. Closing proves a lifecycle transition, not fulfillment or an
  observed result.
- `commitment_close.meta.outcome`, when present, is an unvalidated descriptive
  label on the close. It is not a separate outcome event.
- Existing unversioned `outcome_observation` events describe autonomy action
  results. Their commitment and evidence identifiers are not ledger-validated,
  and their values can contribute to adaptive `policy_update` events.
- A generic `reflection.meta.about_event` is optional and does not establish
  that the reflection is a later review of a commitment outcome.

These facts are the reason for a new versioned relationship. Existing records
must not be reinterpreted as if they already satisfied it.

## Implemented v1 contract

### 1. Exact episode identity

The relationship authority is `open_event_id`.

A v1 commitment outcome must also record `cid` and `close_event_id`, but those
are cross-checks rather than competing identities. Validation must establish:

1. `open_event_id` identifies an existing earlier `commitment_open`;
2. the recorded CID exactly matches that open;
3. `close_event_id` identifies an existing later `commitment_close` whose
   authoritative `meta.open_event_id` is the recorded open and whose CID also
   matches; and
4. `open_event_id < close_event_id < outcome_event_id`.

No CID lookup, latest-episode lookup, text match, or legacy inference may
substitute for the explicit open and close references.

### 2. Outcome observation

A v1 outcome is a canonical `outcome_observation` with protocol
`commitment_outcome.v1`. Its metadata contains exactly the relationship and
producer fields required by this contract: `protocol`, `source`, `cid`,
`open_event_id`, `close_event_id`, and `origin_event_id`. Its content contains
only:

- `observation`: a non-empty textual report of what happened; and
- `evidence_event_ids`: a non-empty, duplicate-free list of canonical event IDs.

Each evidence event must exist and satisfy
`open_event_id < evidence_event_id < outcome_event_id`. This proves bounded
provenance and ordering only; it does not prove evidentiary role or semantic
support.

An episode may have zero or one authoritative v1 outcome. Absence of an outcome
does not keep the episode open. A second distinct outcome for the same
`open_event_id` is rejected; reopening the same CID creates a new episode that
may have its own outcome.

The outcome does not close the commitment, certify fulfillment, or inherit
meaning from `commitment_close.meta.outcome`.

### 3. Later review

A v1 later review is a canonical `reflection` with protocol
`commitment_outcome_review.v1`. Its metadata contains exactly `protocol`,
`source`, `cid`, `open_event_id`, `outcome_event_id`, and `origin_event_id`. Its
content contains only a non-empty `interpretation`.

Validation must establish that the target is an authoritative v1 outcome, that
its recorded episode identity matches the review, and that
`outcome_event_id < review_event_id`.

An outcome may have zero or more distinct later reviews. Reprocessing the same
producer candidate is idempotent, but a genuinely later interpretation is a
new event. A review records an interpretation; it does not revise the outcome,
change commitment state, or become identity or policy authority by itself.

No ordinary reflection becomes a v1 review through content similarity,
`about_event` alone, shared CID text, or temporal proximity.

### 4. Authorized producers

Only a **managed assistant candidate** may create a v1 outcome or review
relationship. The event records an `origin_event_id` identifying an earlier
canonical assistant message containing the exact structured outcome or review
candidate from which it was derived. Its canonical `source` is `assistant`;
other source values are forbidden in v1.

The assistant candidate forms are deliberately narrow:

```text
COMMITMENT_OUTCOME:{"cid":"...","open_event_id":<id>,"close_event_id":<id>,"observation":"...","evidence_event_ids":[...]}
COMMITMENT_REVIEW:{"cid":"...","open_event_id":<id>,"outcome_event_id":<id>,"interpretation":"..."}
```

The canonical writer capability alone is not relationship authority. Generic
append must route protocol-shaped outcome observations and reviews through the
same ledger-aware boundary. Direct operator-authored v1 relationships, user
messages, autonomy source labels, source labels without producer proof, and
forged validation metadata are rejected.

Autonomy-produced commitment outcomes and reviews are deliberately outside v1.
The current `source: autonomy_kernel` label is serializable and therefore cannot
by itself establish producer authority. Supporting that producer requires a
separately authorized, non-forgeable provenance mechanism; existing autonomy
outcome telemetry remains under the legacy rule below.

This contract records the observer/producer. It does not infer a commitment's
obligor or identity subject, which R07/R08 do not presently establish.

### 5. Invalid candidates and idempotency

On every governed path, an invalid v1 candidate produces no canonical
`commitment_outcome.v1` or `commitment_outcome_review.v1` relationship.

- A managed assistant utterance remains canonical history.
- The failed structured attempt is recorded once as a typed
  `validation_failure`, keyed by a stable attempted-payload digest and carrying
  the reason code and proposed references.
- A direct append raises a typed rejection only after the durable failure event
  exists.
- Repeating the same valid candidate converges on the existing canonical event;
  repeating the same invalid candidate converges on the existing failure.

Validation failure must not close or reopen a commitment, create a graph edge,
change adaptive policy, or silently advance an authoritative relationship
projection as if the candidate had succeeded.

### 6. Existing history

There is no migration or inference in v1.

- Existing unversioned `outcome_observation` events remain preserved and retain
  their current legacy adaptive-learning behavior, but they are never attached
  to a `CommitmentEpisode` under this contract.
- Existing `commitment_close.meta.outcome` values remain closure metadata and
  are never promoted or backfilled as v1 outcomes.
- Existing generic reflections remain reflections and are never promoted or
  backfilled as v1 later reviews.
- A later explicit v1 outcome may refer to an already closed legacy episode
  only when the close has an authoritative exact `open_event_id`; inferred
  legacy close relationships are ineligible.

New v1 commitment outcomes must be excluded from the legacy
`extract_outcome_observations` adaptive-learning aggregate. Any future use of
commitment outcomes for policy adaptation requires a separate authorization.

### 7. Authoritative projection and retrieval use

`MemeGraph` is the only new authoritative structural consumer in v1.

- A validated outcome adds an `outcome_for` relationship to its exact open and
  is exposed on that `CommitmentEpisode`.
- A validated later review adds a `reviews_outcome` relationship to its exact
  outcome and is exposed after that outcome in the same episode.
- Episode-aware retrieval may include the validated outcome and reviews only
  when it has independently selected that exact episode, and must retain the
  `open_event_id`, outcome ID, review ID, role, and trigger provenance.

Neither event changes `Mirror` commitment state, closes an episode, updates an
identity projection, or directly changes autonomy thresholds. Other projections
may preserve or ignore the events but may not treat unvalidated or legacy
records as v1 relationships.

## Implemented falsifiable guarantee

> On every governed EventLog path, a `commitment_outcome.v1` relationship may
> become canonical and enter an exact `CommitmentEpisode` only once, after an
> authoritative close of that recorded `open_event_id`, with matching CID,
> authorized producer provenance, and existing ordered evidence. A
> `commitment_outcome_review.v1` relationship may enter that episode only when
> it is a later, authorized reflection on that exact authoritative outcome.
> Otherwise no candidate relationship is appended or projected, and the failed
> attempt is durably preserved as source history and/or one typed validation
> failure. Neither relationship may be inferred from closure, CID equality,
> ordinary reflection, legacy outcome records, or semantic similarity.

The guarantee is falsified by any governed path that:

- promotes an outcome for a missing, open, wrong-CID, or different episode;
- permits two authoritative outcomes for one `open_event_id`;
- promotes a review without the exact earlier authoritative outcome;
- treats an outcome as a close or a review as an identity/policy revision;
- promotes a legacy/unversioned record into the v1 relationship; or
- rejects a candidate without the required preserved history/failure record.

## Implementation disposition

The contract received explicit implementation authorization after policy review.
The governed EventLog boundary, post-initialization RuntimeLoop producer proof,
authoritative cardinality registries, parser, MemeGraph projection,
episode-triggered retrieval provenance, legacy-learning isolation, and
non-promotion checks are implemented without migration or legacy inference.
Invalid protocol-shaped history cannot reserve authority, and relationship
events do not age Mirror state or enter RSM identity bookkeeping.

Post-change lifecycle verification passed the full `575`-test suite, Ruff across
`pmm`, exact-diff whitespace checks, rebuild/incremental comparison, hostile
input counterexamples, and a final hostile exact-diff review with no actionable
high- or medium-severity finding. Publication status is maintained in
`pmm-improvement-progress.md`.
