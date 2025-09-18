"""Directive hierarchy system for PMM.

Deterministic, event-driven system that organizes commitments, policies, and reflections
into a hierarchical directive tree with traceable priority and dependency relationships.
"""

from .directive_hierarchy import DirectiveHierarchy

__all__ = ["DirectiveHierarchy"]
