from dataclasses import dataclass
from typing import Literal, Optional

# Where the directive text came from.
Source = Literal["reply", "reflection"]


@dataclass(frozen=True)
class DirectiveCandidate:
    """
    A normalized directive string detected in assistant output or reflections.
    This is NOT an event. The runtime will turn these into events.
    """

    content: str  # normalized directive text (whitespace-collapsed)
    source: Source  # "reply" | "reflection"
    origin_eid: Optional[int] = (
        None  # event_id of the originating reply/reflection (if known)
    )
