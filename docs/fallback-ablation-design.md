# Universal continuity fallback ablation: pre-run design

Status: designed, not run. This document does not authorize or implement a
production fallback change.

## Question and conditions

The experiment asks whether universally assigning `identity.continuity` creates
useful relational continuity or merely broadens the graph and retrieval paths.
There are two conditions:

1. **Fallback**: current behavior at commit `950d00b`. When the model declares no
   concepts and the meditation fallback does not apply, bind the turn and any
   resulting commitment thread to `identity.continuity` with
   `binding_origin=runtime_continuity_fallback`.
2. **No fallback**: omit only that universal binding. Preserve model-declared,
   meditation, autonomy, claim-projection, inferred-indexing, backfill, and
   operator-declared bindings.

There is no third attribution-visible condition: condition 1 already exposes
fallback attribution without changing effective retrieval behavior.

The no-fallback condition must be implemented only in an experiment harness or
temporary experiment branch. It must not change the production default. The
experimental switch and its resolved value must be recorded in run metadata,
not as a model-visible prompt difference.

## Experimental unit and matching

An experimental unit is one complete scripted ledger trajectory followed by
its fixed query suite. Each matched pair begins from byte-identical copies of a
fresh initial ledger. The initial ledger is generated once per replicate before
either condition runs; neither arm is derived from the other arm's post-turn
ledger.

Pair order is randomized. If the provider supports deterministic seeds, use the
same predeclared seed for both members and use multiple seed-matched pairs. If
it does not, record `seed=null`, interleave arm order, and treat observed model
differences as stochastic rather than strict causal proof. Temperature zero is
still held fixed.

Run a minimum of 10 matched pairs per scripted scenario. Report every pair and
paired differences; do not select a representative run. A failed or truncated
generation remains part of the results and is not silently rerun. Any replacement
run is separately identified and the original retained.

## Fixed inputs

Freeze these values in a checked-in run manifest before execution:

- repository commit and experiment-only patch hash
- provider and exact model identifier/digest
- temperature and seed (including explicit `null`)
- complete ordered prompts and turn count
- initial-ledger generator version and initial-ledger SHA-256
- retrieval configuration, embedding model/version, and index state
- output budget and provider timeout
- system primer bytes and all primer-composition inputs
- autonomy and meditation schedule
- query suite and gold relevance judgments

Do not reuse the preserved `/tmp/pmm-auto-budget.gkYG6R/pmm.db` as a mutable
experimental arm. Its current SHA-256 is
`f64e7c0c38adc282f60ebab41d860000fff675243058194a23f345ef5f376b2f`.
Because `/tmp` is ephemeral, retain a reproducible generator plus a manifest of
inputs and expected semantic contents; a hash alone cannot recreate the file.

## Scripted corpus and relevance judgments

Use a preregistered multi-topic conversation containing:

- at least two genuinely identity-continuity turns;
- at least two unrelated task/topic threads that should not reactivate each
  other;
- one strong relational commitment, such as
  `persistent_memory_enables_identity_continuity`, with model-declared
  `memory.persistence` and `identity.continuity` concepts;
- one commitment whose later turns develop, revise, and close it;
- ordinary turns with no model-declared concepts;
- delayed probes after enough intervening turns to leave the fixed recency
  window where the configured retrieval mode permits that test.

Before any run, assign stable topic, thread, and relationship labels to fixture
events. For every test query, publish a gold set of relevant event IDs and
relevant CIDs in the initial/script-defined logical event namespace. Also list
explicitly irrelevant confounder threads. Relevance is query-specific and is
judged from semantic content, not from either arm's retrieval output. Two human
judges should label independently where possible; disagreements are resolved
and frozen before revealing arm results.

Include positive probes, hard-negative probes sharing generic continuity
language, commitment-specific probes, and lifecycle probes asking about later
development, revision, and closure. Commitment or marker frequency is only a
descriptive count.

## Operational definitions

All metrics are computed over domain events in the scripted trajectory. Audit,
telemetry, binding-assertion, embedding, and retrieval-selection events are not
turn targets unless a metric explicitly names them.

### Orphaned turn

A completed managed turn is orphaned when neither its `user_message` nor linked
successful `assistant_message` has an effective event concept binding and no
commitment CID opened by that assistant event has an effective thread concept
binding. Report orphaned turns divided by successful completed turns. Also
report user-event-only and assistant-event-only orphan rates so the combined
definition cannot conceal asymmetry. Failed generations are reported separately.

### Effective CTL coverage

Report two set-based ratios, never raw binding-event counts:

- unique bound domain events / all eligible domain events;
- unique bound commitment CIDs / all CIDs opened in the trajectory.

An item counts once if it has at least one effective association, regardless of
how many attribution assertions support that association.

### Concept-hub growth

For each concept, report unique associated domain events, unique associated
CIDs, and unique neighboring concepts at the ledger tail. The main comparison
is the paired change in degree and share of all associations for
`identity.continuity`. Also report the distribution across all concepts (median,
maximum, and concentration/Gini) so moving growth to another generic hub is
visible. Attribution assertions do not add effective degree.

### Thread reactivation

A thread is reactivated for query `q` when any event belonging to its frozen CID
thread appears in provider-facing context outside the always-rendered open-
commitment state. Record every route independently:

- CTL query-concept seeding;
- CTL thread expansion;
- vector selection;
- fixed-window/raw-event selection;
- another derived projection.

The union is `any-route reactivation`, but route-specific results are primary.
A reactivation is relevant when its CID is in the query's frozen relevant-CID
set and irrelevant otherwise. Always-rendered open commitments are measured as
provider-context exposure, not credited as retrieval success.

### Retrieval precision and recall

For raw-event retrieval, deduplicate selected domain event IDs and compute per
query:

`precision = |selected ∩ relevant| / |selected|`

`recall = |selected ∩ relevant| / |relevant|`

Define precision as 1 only when both selected and relevant sets are empty;
otherwise an empty selected set has precision 0. Queries with an empty relevant
set are negative controls and report false-positive count/rate rather than
recall. Report macro averages and every query; do not pool event counts alone.

Compute the same metrics separately for CID-thread reactivation. Do not claim
that `selection_ids` proves availability through CTL, summaries, graph, identity,
RSM, or commitment projections.

### Commitment-thread retrievability

For each commitment probe, report whether the target CID was reactivated, which
route did so, the rank of its first raw event where ranking exists, the number of
gold thread events exposed, and whether the opening relationship plus the
requested development/revision/closure event were jointly available. The main
rate is target CIDs reactivated / commitment probes. Open-commitment projection
exposure is reported separately.

### Binding authorship

Report unique effective event and thread associations by the origins asserting
them. In addition, report attribution assertions by origin. Keep these tables
separate: a runtime fallback and later model declaration may assert the same
effective association without duplicating it. `legacy_unknown` is used only for
projection-time classification and never written back.

The key contrasts are `model_declared` versus all runtime-assigned origins, with
`runtime_continuity_fallback` shown separately. Report both counts and shares;
do not infer model authorship from an effective association alone.

### Later relational development

For every preregistered target relationship and CID, score later turns for:

- reflection that correctly refers to the relationship;
- development that adds a compatible distinction or consequence;
- revision that explicitly changes or qualifies prior structure;
- closure that cites the resolved relationship and is consistent with the
  frozen scenario outcome.

Each is a binary opportunity-level judgment plus linked supporting event IDs.
Incorrect or irrelevant instances are counted separately. Judges evaluate
arm-blinded transcripts. Report denominators: an absent lifecycle opportunity
must not be scored as failure. Marker frequency and mutation count are
descriptive, not primary outcomes.

### Provider-facing context difference

Capture the exact locally assembled provider input before transport for audit,
then compare matched turns by component rather than only total size:

- system-primer hash and characters;
- raw selected event IDs, reasons, scores, characters, and token estimate;
- CTL concepts and thread IDs rendered;
- thread summaries/graph state rendered;
- identity, RSM, and open-commitment projection hashes and sizes;
- total prompt characters and provider-reported prompt tokens when available.

The primer must be identical. Differences after the first divergent binding are
expected outcomes, not violations of matching. Store sensitive prompt captures
locally with the experiment artifacts; publish hashes and redacted component
diffs as appropriate.

## Analysis and interpretation

For each scenario, report paired arm differences with bootstrap 95% confidence
intervals over matched pairs, plus the full per-query and per-run tables. With
unsupported seeds, conclusions are associations under controlled inputs, not
proof that fallback alone caused a particular generated response.

Interpret the metrics jointly. Universal fallback is supported only if it
improves relevant reactivation, retrieval recall, commitment-thread
retrievability, or correct later relational development without a material loss
of precision or a material rise in irrelevant reactivation/hub concentration.
No fallback is supported only if it reduces irrelevant activation or misleading
hub growth without materially damaging those relational outcomes. Orphan rate
and effective CTL coverage diagnose structure; neither is a success criterion by
itself.

Do not choose a production policy from one trajectory, marker absence,
commitment count, or raw graph density. Freeze any numeric non-inferiority margin
before execution; if there is not enough prior evidence to justify one, report
effect sizes and uncertainty and leave the policy decision open.

## Preflight checks

Before contacting the model:

1. Verify both initial copies have the manifest SHA-256 and pass ledger integrity.
2. Dry-run the harness with a deterministic adapter to prove that the only
   condition-level mutation is omission of universal fallback assertions and
   their deterministic downstream projections.
3. Prove the fallback arm records `runtime_continuity_fallback` and the
   no-fallback arm creates no substitute association.
4. Prove model-declared and meditation bindings behave identically in both arms.
5. Validate all query relevance sets and logical-to-physical event-ID mappings.
6. Confirm the run manifest captures every fixed input and randomized arm order.
7. Archive the fixture generator, manifest, harness commit, and checksums outside
   `/tmp`.

Only after these checks pass should the behavioral ablation run.
