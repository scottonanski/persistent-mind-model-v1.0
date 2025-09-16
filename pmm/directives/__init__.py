# Re-export public API for convenience.
from .types import DirectiveCandidate, Source  # noqa: F401
from .detector import extract  # noqa: F401

# Initialize the directives module

from .classifier import SemanticDirectiveClassifier as SemanticDirectiveClassifier
from .hierarchy import (
    DirectiveHierarchy as DirectiveHierarchy,
    Directive as Directive,
    MetaPrinciple as MetaPrinciple,
    Principle as Principle,
    Commitment as Commitment,
)
