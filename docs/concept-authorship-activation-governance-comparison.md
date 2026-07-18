# Concept authorship: direct activation versus provisional growth

Status: design-only comparison using preserved experimental outputs. It does not
choose an architecture or authorize production implementation.

## Evidence scenarios

This comparison models five cases:

1. **Granite false triggers:** the ten structurally accepted v2.5 negative
   declarations—basil and arithmetic in 5/5 repetitions each. Across independent
   trial calls these contained twenty inappropriate definitions. In one sequential
   ledger, repeated identical definitions would commonly reject after their first
   definition; they are still ten demonstrated opportunities for unsafe mutation,
   and varied tokens could evade that incidental deduplication.
2. **Gemma appropriate growth:** 29 structurally accepted v2.5 positive emissions,
   zero negative declarations, and definitions scoring 1.93/2 relevance and
   1.87/2 relational quality.
3. **Compatible-model false positive:** a modeled unseen prompt causes an otherwise
   compatible configuration to propose an ordinary topic such as
   `gardening.moisture_management`. This was not observed for Gemma in v2.5; it
   represents the finite-corpus risk that attestation cannot eliminate.
4. **Long-lived unresolved proposals:** proposals receive no natural recurrence,
   reflection, or operator attention for many managed turns.
5. **Model replacement:** the active model changes while proposals from a prior
   configuration remain unresolved.

Attestation means only that a frozen configuration passed frozen evidence. It is
not a guarantee of permanently correct judgment on unseen prompts.

## Option A: attested direct activation

A configuration that matches an approved compatibility attestation may submit a
fresh, structurally valid declaration. Accepted definitions and current-turn
bindings immediately enter effective CTL projections.

### Effects

- **Ledger and projections:** `concept_define` and binding events become effective
  immediately. ConceptGraph, thread aggregation, retrieval seeding, summaries,
  lifetime memory, and later autonomous processing can observe downstream effects.
- **Pollution risk:** an attested model's plausible false positive can become a
  semantic hub before anyone reviews it. Granite is denied authority, so its ten
  demonstrated false triggers produce no concept events.
- **Promotion:** none beyond structural/freshness validation and prior capability
  attestation.
- **Stalling:** not applicable; activation is immediate.
- **Rejection record:** structurally invalid or unauthorized controls should create
  typed diagnostics but no CTL mutation.
- **Model switch:** authority must be re-evaluated before composing the next prompt.
  Existing concepts remain active and retain original authorship attribution.
- **Recovery:** mistaken activation requires explicit revision, deprecation,
  unbinding, or supersession. Earlier retrieval and summaries may already have
  propagated it; immutable history must record both mistake and correction.
- **External complexity:** high. Trust anchors, immutable configuration identity,
  approval, expiry, renewal, revocation, hosted-model drift, and switch-time checks
  are required. Even perfect administration cannot cover unseen semantic errors.

### Scenario outcome

Gemma's 29 appropriate emissions become useful CTL immediately. Granite's ten
negative declarations are excluded if gating works. The modeled Gemma false
positive activates immediately and must later be repaired.

## Option B: universal provisional authorship

Any structurally valid, fresh declaration creates immutable proposal events, not
effective CTL definitions or bindings. A later lifecycle may promote, reject, or
expire them.

This option sidesteps pre-authorization for semantic mutation; it does not make
all models trustworthy and does not eliminate the need for structural protocol
compatibility.

### Effects

- **Ledger and projections:** proposals enter an append-only proposal ledger and a
  separate bounded review projection. Pending tokens must not enter effective
  ConceptGraph, MemeGraph, normal CTL retrieval seeding, identity, RSM, ordinary
  summaries, lifetime memory, open commitments, or autonomous attention.
- **Pollution risk:** ordinary cognition is protected only if this separation is
  strict. The review projection itself can still be flooded by Granite-style
  overuse. Storage is cheap; review attention and prompt space are not.
- **Promotion:** possible evidence includes recurrence on independent turns,
  retrieval-backed reflection, meaningful commitment development, cross-model
  rediscovery, operator ratification, or another explicitly defined anchor. A
  model must not silently self-ratify merely by repeating the same payload.
- **Stalling:** unresolved proposals can remain pending forever unless the protocol
  has deterministic expiry. Expiry should use managed-turn distance rather than
  wall-clock time and append an explicit expiry event; immutable proposal history
  remains.
- **Rejection/closure:** `proposal_promote`, `proposal_reject`, and
  `proposal_expire` events should reference the proposal, evidence, reviewer or
  process, reason, and governing policy version. No event is rewritten.
- **Model switch:** proposals retain originating configuration and assistant event.
  A replacement model may supply independent evidence or review, but authorship is
  not relabeled and unresolved proposals do not become active merely because the
  interpreter changed.
- **Recovery:** rejection or expiry prevents ordinary CTL effects. A mistaken
  promotion still needs the same explicit revision/deprecation path as direct
  activation.
- **External complexity:** lower pre-authorization burden but substantially more
  lifecycle machinery: proposal schemas, bounded projection, scheduling,
  promotion policy, anti-spam controls, expiry, review provenance, and recovery.

### Bounded visibility requirement

Completely invisible proposals cannot be reconsidered; broadly visible proposals
pollute cognition. A viable provisional design therefore needs a dedicated review
projection with all of these constraints:

- excluded from ordinary retrieval, CTL seeding, summaries, and model context;
- exposed only to designated proposal-review reflections or explicit operator
  inspection;
- capped per review by count and token budget;
- grouped by canonical proposal digest so repetition raises recurrence evidence
  without multiplying prompt entries;
- rate-limited per origin configuration and semantic neighborhood;
- scheduled deterministically so pending proposals cannot monopolize reflection;
- expired or rejected explicitly when evidence does not develop.

This makes reconsideration possible without turning Granite's basil spam into a
semantic hub. It also introduces a risk of silent stalling: a good Gemma proposal
may expire because no designated review occurs, even though ordinary conversation
would have benefited from immediate activation.

### Scenario outcome

Gemma's 29 appropriate emissions initially remain unavailable to ordinary CTL,
reducing their immediate retrieval value. Granite's ten unsafe declarations become
proposal events; canonical grouping can reduce review entries, but distinct
inappropriate tokens can still consume review attention. The modeled compatible-
model false positive is contained unless mistakenly promoted. Long-lived proposals
expire visibly. Model replacement does not erase or silently inherit them.

## Comparative matrix

| Dimension | Attested direct activation | Universal provisional authorship |
|---|---|---|
| Good concept availability | Immediate | Delayed until promotion |
| Bad concept ordinary CTL effect | Immediate until corrected | None while pending, if projections are isolated |
| Granite v2.5 overuse | Blocked by capability gate | Recorded as proposal pressure |
| Compatible-model unseen error | Activates | Contained unless promoted |
| Cognitive pollution | Effective graph/retrieval | Review queue and lifecycle attention |
| Stalling | No | Yes; requires deterministic expiry/review |
| Recovery cost | High after activation | Low before promotion; high after mistaken promotion |
| Model-switch requirement | Re-attest before prompt | Preserve origin; review semantics required |
| External trust infrastructure | High | Lower, but not zero |
| Internal lifecycle complexity | Lower | High |
| PMM relational development | Immediate but risky | Explicitly developmental but slower |

## No winner yet

The choice is not “safe” versus “unsafe.” It is between:

- imperfectly pre-authorizing configurations and repairing occasional effective
  mistakes; and
- admitting imperfect proposals into a quarantined lifecycle and paying review,
  stalling, expiry, and delayed-utility costs.

Before choosing, a mechanistic nonproduction simulation should replay the actual
v2.5 declarations through both projection policies and measure:

- effective ConceptGraph and retrieval changes;
- proposal-review queue size after canonical grouping and rate limits;
- provider-context token cost for designated reviews;
- time-to-promotion for Gemma's appropriate definitions;
- false-promotion and false-expiry scenarios;
- recovery events required after one mistaken activation;
- behavior across a model switch with pending proposals.

No production parser should be built from this comparison alone. The v3 result
also shows that freshness may be better separated from free-form semantic judgment
rather than taught as additional control prose.

