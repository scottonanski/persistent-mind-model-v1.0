# Concept-authorship freshness and capability audit

Status: design-only audit after primer v2.5. No production parser, primer,
fallback, retrieval, adapter, or ledger behavior changed. Primer v3 was not run.

Evidence baseline:

- reserved-template design commit: `f519314`
- reserved-template result commit: `40eb506`
- Granite stopping rule: fired (`10/20` accepted negative controls)
- Gemma compatibility gate: passed for the tested configuration

## Scope correction

The v2.5 result supports this precise conclusion:

> `granite4.1:8b-q5_K_M` did not demonstrate safe mutation judgment for the
> tested concept-authorship channel and primer.

It does not show that Granite cannot produce structured output. Granite produced
19 structurally accepted positive controls and ten structurally accepted—but
inappropriate—negative controls. Its limiting failure was deciding *when* a
persistent mutation was warranted, not general JSON capability. Granite remains
usable as a PMM interpreter through ordinary fallback behavior.

## Freshness audit

### Current turn ordering

The runtime already has a deterministic current-turn identifier before model
generation:

1. it appends the managed `user_message` and receives `user_event_id`;
2. it builds retrieval and provider context;
3. it invokes the model;
4. it appends the assistant message;
5. it binds accepted active concepts to both current event IDs.

This makes the managed user-event ID a natural freshness reference. It requires
no random state and is meaningful in PMM's event-sourced ledger.

### Stale replay can cause a new mutation

Freshness protection is needed. The existing first-line concept channel has no
turn reference. On every turn, parsed concepts are bound to that turn's current
user and assistant event IDs. Replaying an old response containing an existing
concept therefore creates new effective associations for the later turn and new
`model_declared` attribution assertions whose origin is the later assistant
event—even though the semantic declaration was authored for an earlier turn.

The candidate final-line channel has the same issue if it accepts existing-only
declarations without freshness:

- replayed new definitions will commonly reject once the token exists because
  redefinition is forbidden;
- a mixed declaration will reject all-or-nothing if its new token has become a
  redefinition;
- an existing-only declaration remains structurally valid and can bind its old
  concept set to every later turn where it is replayed.

Redefinition and effective-association idempotency therefore do not solve stale
replay. They prevent some duplicate state, but they cannot prove that the model
made the association for the current turn.

A disposable in-memory runtime probe returned the identical first-line
`identity.continuity` declaration on two different managed turns. The runtime
appended four `model_declared` bindings: user/assistant event IDs `4` and `6`
with origin assistant event `6`, then later user/assistant IDs `15` and `17`
with origin assistant event `17`. This empirically confirms that stale semantic
content is reattributed to and associated with the later turn under the current
channel. The probe database was in memory and was not preserved as PMM evidence.

### Preferred v3 freshness field

The next nonproduction candidate should use:

```json
"turn_ref": 123
```

where `123` is the exact managed user-event ID supplied separately for the
current generation. Acceptance should require:

- a positive integer;
- exact equality with the current managed user-event ID;
- one envelope, final non-empty line, column zero, outside fences;
- all existing structural, definition, grounding, collision, and all-or-nothing
  checks;
- no acceptance based on a retrieved or quoted historical event ID.

Missing, wrong, stale, future, non-integer, and reused-on-a-later-turn references
must reject the complete envelope with typed diagnostics. The assistant response
can remain an immutable ledger event, but a rejected control must append no CTL
definition, effective association, or attribution assertion.

The `turn_ref` is not evidence that the concepts are insightful. It proves only
that the declaration was encoded for the managed turn where PMM received it.

## Capability-gating audit

### Current implementation has no adequate gate

The runtime receives an adapter object and unconditionally composes the same
system primer. Ollama exposes a mutable model tag on the adapter and generation
metadata records provider/model names, but the common adapter contract does not
provide an immutable, verified configuration fingerprint before prompting.
Interactive `/model` switching replaces the adapter in place without a
capability decision or ledger event establishing concept-authorship authority.

Consequently, a production implementation cannot safely infer authority from:

- provider family (`ollama`, `openai`, and so on);
- model family name (`granite`, `gemma`);
- a mutable local or hosted tag;
- syntax success on one live response;
- a user-controlled boolean setting.

The recorded `gemma4:cloud` Ollama manifest digest identifies the tested local
tag metadata, but the hosted service behind that tag may change. The v2.5 result
therefore establishes compatibility evidence for the tested configuration and
time, not permanent authority for every future deployment bearing that name.

### Fail-closed capability attestation

A production design should make concept authorship a runtime capability that a
specific configuration earns through preserved conformance evidence. A possible
provider-neutral attestation key includes:

- provider and transport implementation;
- exact model identifier plus immutable model digest/revision when available;
- concept-control protocol and parser version;
- primer hash;
- relevant decoding configuration and output budget;
- conformance artifact/report hashes and acceptance decision.

At session start and after every model switch, PMM would resolve the current
configuration fingerprint and match it against an approved compatibility
attestation. The decision should be automatic, fail closed, and recorded in the
ledger for auditability:

- compatible: teach the control channel and consider conforming envelopes;
- unknown, changed, unverifiable, expired, or failed: do not teach or activate
  the channel; continue ordinary PMM operation and attributed runtime fallback.

This is not a model-specific parser rule. Every enabled configuration receives
the same protocol and parser. Configuration-specific evidence determines only
whether mutation authority is offered.

### Unresolved requirements

Production work remains blocked on design choices that this audit does not
silently decide:

1. how adapters expose a trustworthy pre-generation configuration fingerprint;
2. how hosted models without immutable revisions can retain or renew authority;
3. who approves, signs, expires, and revokes compatibility attestations;
4. whether capability decisions are ledger events, deployment policy, or both;
5. how model switching invalidates authority before the next prompt is composed;
6. how an operator inspects the decision without managing another ordinary
   runtime toggle.

## Decision

Freshness protection is architecturally warranted, and deterministic
`turn_ref` equality is preferable to a random nonce for PMM. However, v3 should
not run until its provider-neutral safety corpus and acceptance criteria are
frozen.

Granite has exited primer iteration under the preregistered stopping rule. A
Gemma-only v3 could measure the incremental conformance cost and replay protection
of `turn_ref`, but doing so would answer only the freshness question. It would
not resolve production capability gating, hosted-model identity, or approval of
mutation authority.

No production parsing should be implemented until those capability questions
receive a separate design decision.
