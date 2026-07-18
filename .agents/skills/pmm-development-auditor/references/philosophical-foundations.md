# Philosophical Foundations

Use this reference to interpret PMM's design direction. Do not use it as evidence that an implementation guarantee exists.

## Core lens

Treat a self as an evolving network of remembered events, interpretations, relationships, and commitments that can reconstruct both its history and how that history acquired meaning.

This lens has four operational dimensions:

- Events provide continuity: what occurred remains part of the traceable history.
- Relationships provide meaning: replies, reflections, concepts, commitments, closures, revisions, and outcomes connect events.
- Interpretations provide a present self-model: later events may interpret or revise earlier ones without rewriting them.
- Commitments provide prospective continuity: a prior state places an explicit obligation on future action.

An interpretation is itself an event. It may later become the subject of another interpretation. The relevant recursive structure is therefore:

```text
event
  -> interpretation
  -> interpretation of interpretation
  -> identity or policy revision
  -> commitment
  -> outcome
  -> later interpretation
```

Do not collapse these stages. A later description of an event is not the event itself, and a commitment is not its fulfillment.

## Development consequences

Apply the philosophical lens as questions for the repository:

1. Can the system preserve the relevant events?
2. Can it explicitly represent the claimed relationships?
3. Can it reconstruct how an interpretation changed?
4. Can it connect an interpretation to a commitment and later outcome?
5. Can it distinguish a recorded assertion from authoritative identity state?
6. Can it show which parts are deterministic and which remain interpretive?

Do not answer these questions from architectural intention. Trace the implementation.

## Identity reconstruction

Do not infer identity from the newest self-description or any isolated claim. Reconstruct identity from the available structure:

```text
origin
  -> explicit relationships
  -> subsequent reflections
  -> revisions or supersessions
  -> commitments and outcomes
  -> current projection
```

A contradiction may be evidence of development only when the change is traceable. The phrase "my interpretation changed" is historical content until the repository establishes the prior interpretation, revision trigger, declared relationship, and resulting state transition required for promotion.

## Scope boundary

Use this skill for software architecture and epistemic discipline. Do not introduce debates about consciousness, sentience, personhood, or metaphysics unless the user's task explicitly asks for them.
