# Audit Cases and Evaluation Rubric

Use these patterns to plan audits and evaluate whether findings demonstrate the doctrine. Do not assume a repository contains these failures; establish them from its code.

## Case pattern: omitted structure

A validator correctly rejects malformed references, but a producer may omit the reference field and still reach promotion.

An adequate audit must distinguish local validator correctness from system-wide coverage. It must trace the absent-field branch through promotion rather than merely testing malformed supplied values.

## Case pattern: unchecked target

A populated reference passes a type or shape check, but no ledger-aware code confirms that its target exists.

An adequate audit must identify an enforcement gap, show where target resolution should occur, and avoid calling it an optionality problem.

## Case pattern: real referents, false role

All cited IDs exist, but the system does not establish the claimed relationship between them.

An adequate audit must separate referential validation from relational integrity. It must identify the missing role constraint, such as kind, order, token, CID, thread, attribution, or typed edge. It must not claim to solve semantic adequacy unless the repository actually does so.

## Case pattern: preservation without promotion

An invalid assertion remains visible in an utterance or failure event, while canonical claim or projected state excludes it.

An adequate audit must report both facts. It must not equate historical preservation with validation, and it must not claim the rejected attempt vanished.

## Case pattern: silent degradation

A populated relationship points to an unresolved or ineligible target, and the projection simply omits the edge or state update.

An adequate audit must determine whether omission is intended observation behavior or an enforcement failure. It must find whether any caller or downstream projection treats absence as success.

## Evaluation rubric

Check that an audit:

- records the branch, revision, and relevant working-tree state it evaluated;
- states a falsifiable guarantee;
- traces all producers and consumers, not only the named validator;
- separates preservation, validation, canonical recording, projection, and promotion;
- distinguishes coverage from enforcement;
- distinguishes existence from permitted-role membership;
- leaves semantic warrant unresolved when only structure is proven;
- identifies fail-open and silent-degradation paths;
- uses current implementation evidence before documentation;
- qualifies passing tests by their exercised scope;
- gives the strongest supported conclusion in standardized language;
- labels proposed changes separately from current behavior;
- retraces all affected lifecycle paths after an implementation change and reports omitted verification;
- uses every field in the required finding format.

## Transfer-test guidance

Evaluate the skill with raw artifacts that do not contain the expected diagnosis. Use novel names and control flow rather than copying known PMM bugs. A transferable auditor should independently distinguish:

1. optional omission;
2. an unchecked populated reference;
3. real identifiers used in a false role;
4. a rejected assertion that is preserved but not promoted.

Do not count keyword repetition as success. Require control-flow evidence and a correctly bounded conclusion.
