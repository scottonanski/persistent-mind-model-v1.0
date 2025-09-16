from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
import logging

from pmm.storage.eventlog import EventLog
from pmm.directives.classifier import SemanticDirectiveClassifier

logger = logging.getLogger(__name__)


@dataclass
class Directive:
    """Base class for all directive types."""

    id: str
    content: str
    created_at: str
    source_event_id: Optional[str] = None
    confidence: float = 0.0
    directive_type: str = "commitment"


@dataclass
class MetaPrinciple(Directive):
    """Rules about how to evolve principles and commitments."""

    triggers_evolution: bool = True
    evolution_scope: str = "framework"
    directive_type: str = "meta-principle"


@dataclass
class Principle(Directive):
    """Identity-defining guidelines that govern behavior."""

    parent_meta_principle: Optional[str] = None
    permanence_level: str = "high"
    directive_type: str = "principle"


@dataclass
class Commitment(Directive):
    """Specific behavioral intentions."""

    parent_principle: Optional[str] = None
    behavioral_scope: str = "specific"
    directive_type: str = "commitment"


class DirectiveHierarchy:
    """
    Manages the hierarchical relationship between directives.
    Handles natural evolution from commitments → principles → meta-principles.
    """

    def __init__(self, eventlog: Optional[EventLog] = None):
        self.eventlog = eventlog
        self.classifier = SemanticDirectiveClassifier(eventlog)
        self.meta_principles: Dict[str, MetaPrinciple] = {}
        self.principles: Dict[str, Principle] = {}
        self.commitments: Dict[str, Commitment] = {}
        self.relationships: Dict[str, Dict[str, List[str]]] = {
            "meta_to_principles": {},
            "principle_to_commitments": {},
        }
        self._next_id = 0

    def _generate_id(self) -> str:
        """Generate a unique ID for a directive."""
        self._next_id += 1
        return f"DIR-{self._next_id:04d}"

    def add_directive(
        self, text: str, source_event_id: Optional[str] = None
    ) -> Optional[Directive]:
        """
        Add a directive to the hierarchy after classifying it.

        Args:
            text: The text content of the directive.
            source_event_id: Optional ID of the source event.

        Returns:
            The created Directive object (or subclass) if added, None otherwise.
        """
        if not text or not isinstance(text, str):
            return None

        # Classify the directive using the classifier
        classification = self.classifier.classify_directive(text)
        directive_type = classification["type"]
        confidence = classification["confidence"]

        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        directive_id = self._generate_id()

        directive = None
        if directive_type == "meta-principle":
            directive = MetaPrinciple(
                id=directive_id,
                content=text,
                created_at=created_at,
                source_event_id=source_event_id,
                confidence=confidence,
            )
            self.meta_principles[directive_id] = directive
            self.relationships["meta_to_principles"][directive_id] = []
        elif directive_type == "principle":
            directive = Principle(
                id=directive_id,
                content=text,
                created_at=created_at,
                source_event_id=source_event_id,
                confidence=confidence,
            )
            self.principles[directive_id] = directive
            self.relationships["principle_to_commitments"][directive_id] = []
            # Optionally link to a meta-principle (placeholder logic)
            if self.meta_principles:
                meta_id = list(self.meta_principles.keys())[
                    0
                ]  # Simple selection for demo
                self.relationships["meta_to_principles"][meta_id].append(directive_id)
                directive.parent_meta_principle = meta_id
        else:  # commitment
            directive = Commitment(
                id=directive_id,
                content=text,
                created_at=created_at,
                source_event_id=source_event_id,
                confidence=confidence,
            )
            self.commitments[directive_id] = directive
            # Optionally link to a principle (placeholder logic)
            if self.principles:
                principle_id = list(self.principles.keys())[
                    0
                ]  # Simple selection for demo
                self.relationships["principle_to_commitments"][principle_id].append(
                    directive_id
                )
                directive.parent_principle = principle_id

        # Log directive addition to EventLog if available
        if self.eventlog:
            self.eventlog.append(
                kind="directive_added",
                content=text,
                meta={
                    "id": directive_id,
                    "type": directive_type,
                    "confidence": confidence,
                    "created_at": created_at,
                    "source_event_id": source_event_id if source_event_id else "",
                },
            )

        return directive

    def get_directive_relationships(self) -> Dict[str, Dict[str, List[str]]]:
        """
        Get the current relationships between directives.

        Returns:
            A dictionary representing the hierarchy relationships.
        """
        return self.relationships

    def get_all_directives(self) -> List[Directive]:
        """
        Get all directives in the hierarchy.

        Returns:
            A list of all Directive objects (including subclasses).
        """
        all_directives: List[Directive] = []
        all_directives.extend(self.meta_principles.values())
        all_directives.extend(self.principles.values())
        all_directives.extend(self.commitments.values())
        return all_directives

    def get_directive_by_id(self, directive_id: str) -> Optional[Directive]:
        """
        Retrieve a directive by its ID.

        Args:
            directive_id: The ID of the directive to retrieve.

        Returns:
            The Directive object if found, None otherwise.
        """
        if directive_id in self.meta_principles:
            return self.meta_principles[directive_id]
        elif directive_id in self.principles:
            return self.principles[directive_id]
        elif directive_id in self.commitments:
            return self.commitments[directive_id]
        return None
