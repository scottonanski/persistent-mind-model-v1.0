# Integrity and Promotion

Use this reference to classify what PMM records, validates, projects, and treats as authoritative.

## Separate the lifecycle layers

Do not use "stored" or "accepted" without identifying the layer:

1. **Utterance history**: preserve what a user or model emitted.
2. **Extracted candidate**: recognize structured material inside that utterance.
3. **Validation result**: accept or reject the candidate under a named policy.
4. **Canonical event**: append a typed event representing accepted structure, or append a distinct failure event for a rejected attempt.
5. **Projection**: consume canonical events into rebuildable state such as commitments, concepts, or identity.
6. **Authoritative promotion**: permit the structure to change the state used for later reasoning or action.

A historical utterance is not automatically a canonical claim. A canonical event is not automatically consumed by every projection. A projection is not proof of semantic truth.

## Distinguish gap mechanics

### Coverage gap

A path that should be checked can omit or bypass the check. Typical indicators include:

- optional evidence on a claim whose promotion requires grounding;
- a direct producer that does not call the validator;
- a compatibility path with weaker requirements;
- validation only when a key is present;
- a default that treats absence as success.

### Enforcement gap

Supplied structure is checked incompletely or not checked against repository state. Typical indicators include:

- checking that an ID is an integer but not that it exists;
- accepting a target that exists without checking its event or concept kind;
- silently dropping an unresolved edge;
- accepting any intervening event as an anchor;
- type-checking a supersession pointer without validating its target.

A guarantee may contain both kinds of gap. Report them independently.

Use invocation as the boundary: if a relevant producer or promotion path can avoid the applicable validator, report a coverage gap. If every in-scope path invokes the validator but the validator omits an existence, target, role, or state predicate, report an enforcement gap instead. A conditional absent-field branch is a coverage gap when omission skips a check required for promotion.

## Classify integrity levels

### Referential validation

Ask whether each declared referent exists and was available under the applicable policy. This may include ledger existence, retrieval selection, and valid identifier structure.

Existence does not establish role.

### Relational integrity

Ask whether the referent is permitted to serve the declared role relative to the referrer. Deterministic checks may include:

- event ordering;
- target kind;
- same token, CID, concept version, or thread;
- required typed edge;
- binding attribution;
- role cardinality;
- absence of cycles or invalid supersession.

Role membership does not establish semantic warrant.

### Semantic adequacy

Ask whether the referenced content genuinely supports the claim or interpretation. Keep this unresolved when the repository establishes only structure. Do not substitute an unverified second model judgment as authoritative proof.

### Governance integrity

Ask which actors, sources, and paths may create, bind, validate, or promote the structure. Trace enforcement rather than trusting source labels.

## Apply the evidence hierarchy

Rank evidence as follows:

1. Current production code paths.
2. Schemas and deterministic projections.
3. Tests exercising those paths.
4. Runtime or ledger evidence.
5. Documentation and design artifacts.
6. Model or agent descriptions.

Passing tests prove behavior only under their fixtures and paths. A code path that avoids the tested mechanism limits the strongest supported conclusion.

## Use scoped status language

Choose the strongest status justified by every relevant path:

- **implemented and mandatory**: all in-scope producers and promotion paths enforce it;
- **implemented only when explicitly invoked**: the mechanism works, but invocation is optional or incomplete;
- **partially enforced**: some paths or required properties are checked and others are not;
- **structurally validated but relationally unproven**: references or fields pass structural checks without permitted-role proof;
- **documented but not implemented**: prose describes an absent invariant;
- **proposed invariant**: a design choice has not shipped;
- **unresolved semantic question**: deterministic structure cannot establish warrant.

When paths differ, report the weaker system-wide status and describe stronger local paths separately.

## Preserve unsettled policy

Identify but do not autonomously settle:

- which structures require references for authoritative promotion;
- the complete registered claim-type set;
- permitted relation roles and cardinalities;
- whether unsupported proposals become canonical claims or remain only utterance history;
- how semantic adequacy is adjudicated;
- which graph edges may govern promotion.

Existence policy belongs to referential validation. Same-thread, same-token, same-version, kind, ordering, or role policy belongs to relational integrity.
