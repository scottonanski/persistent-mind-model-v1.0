# pmm/constants.py


class EventKinds:
    """Constants for event kinds to replace string literals."""

    # Core commitment lifecycle
    COMMITMENT_OPEN = "commitment_open"
    COMMITMENT_CLOSE = "commitment_close"
    EVIDENCE_CANDIDATE = "evidence_candidate"

    # Reflection and introspection
    REFLECTION = "reflection"
    INTROSPECTION_QUERY = "introspection_query"
    INTROSPECTION_REPORT = "introspection_report"

    # Identity and traits
    TRAIT_UPDATE = "trait_update"
    IDENTITY_ADOPTION = "identity_adoption"

    # Audit and reporting
    AUDIT_REPORT = "audit_report"
    EVOLUTION = "evolution"

    # System events
    COMMITMENT_RESTRUCTURE = "commitment_restructure"
    DIRECTIVE_HIERARCHY = "directive_hierarchy"
    PATTERN_CONTINUITY = "pattern_continuity"
