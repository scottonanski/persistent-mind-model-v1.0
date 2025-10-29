"""Commitment intent exemplars for semantic classification.

Versioned exemplar lists used by the deterministic semantic detector.
Exemplars should be concise, unambiguous, and auditable.
"""

from __future__ import annotations

# Explicit exemplar phrases grouped by intent. Keep short and generic.
COMMITMENT_EXEMPLARS: dict[str, list[str]] = {
    # First-person pledges or explicit commitment statements
    "open": [
        "I will finish the documentation by Friday",
        "I committed to finishing the documentation by Friday",
        "I committed to finishing the documentation",
        "I committed to helping with this feature",
        "I'm going to complete this task",
        "I've decided to work on this",
        "I'll make sure to do this",
        "I plan to refactor the module",
        "My commitment is to deliver quality code",
        "This is my commitment to the project",
        "I need to fix these bugs",
        "I should implement error handling",
        "I must complete the review process",
    ],
    # Descriptive/adjectival uses (not pledges)
    "adjectival": [
        "My ideal self is committed to accuracy",
        "An assistant committed to helping users",
        "The system is committed to maintaining state",
        "A model committed to transparency",
        "This approach is committed to clarity",
        "Software committed to memory",
        "We are committed to open source",
        "The team committed the changes",
    ],
    # Completed/closed statements (not opening new commitments)
    "closed": [
        "I finished the documentation yesterday",
        "I completed the implementation",
        "I resolved all the test failures",
        "The task is done",
    ],
}
