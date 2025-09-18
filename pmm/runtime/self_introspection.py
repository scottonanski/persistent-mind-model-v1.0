# pmm/runtime/self_introspection.py

import hashlib
from typing import Dict, List, Any
from pmm.storage.eventlog import EventLog
from pmm.constants import EventKinds


def _digest_events(events: List[Dict[str, Any]]) -> str:
    """Produce deterministic digest for a set of events."""
    m = hashlib.sha256()
    for e in events:
        # Only stable fields, no volatile timestamps
        m.update(str(e.get("kind")).encode())
        m.update(str(e.get("content")).encode())
        m.update(str(e.get("meta", {})).encode())
    return m.hexdigest()


class SelfIntrospection:
    """Schema-safe, deterministic introspection over the event log."""

    def __init__(self, log: EventLog):
        self.log = log

    def query_commitments(self, window: int = 50) -> Dict[str, Any]:
        """Return recent commitments grouped by digest."""
        events = [
            e
            for e in self.log.read_tail(limit=window)
            if e["kind"] == EventKinds.COMMITMENT_OPEN
            or e["kind"] == EventKinds.COMMITMENT_CLOSE
        ]
        result = {}
        for e in events:
            digest = _digest_events([e])
            meta = e.get("meta", {})
            result[digest] = {
                "cid": meta.get("cid"),
                "text": meta.get("text") or e.get("content"),
                "status": meta.get("status"),
                "kind": e.get("kind"),
                "id": e.get("id"),
            }
        return {"commitments": result, "digest": _digest_events(events)}

    def analyze_reflections(self, window: int = 20) -> Dict[str, Any]:
        """Summarize recent reflections deterministically."""
        events = [
            e
            for e in self.log.read_tail(limit=window)
            if e["kind"] == EventKinds.REFLECTION
        ]
        summaries = []
        for e in events:
            meta = e.get("meta", {})
            summaries.append(
                {
                    "rid": meta.get("rid") or e.get("id"),
                    "insight": e.get("content"),
                    "topic": meta.get("topic"),
                    "id": e.get("id"),
                }
            )
        return {"reflections": summaries, "digest": _digest_events(events)}

    def track_traits(self, window: int = 100) -> Dict[str, Any]:
        """Track deterministic trait drift."""
        events = [
            e
            for e in self.log.read_tail(limit=window)
            if e["kind"] == EventKinds.TRAIT_UPDATE
        ]
        deltas = {}
        for e in events:
            meta = e.get("meta", {})
            trait = meta.get("trait")
            if trait:
                deltas.setdefault(trait, []).append(
                    {
                        "value": e.get("content"),
                        "reason": meta.get("reason"),
                        "id": e.get("id"),
                    }
                )
        return {"traits": deltas, "digest": _digest_events(events)}

    def emit_query_event(self, kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Emit an introspection_query event with digest idempotency."""
        digest = payload["digest"]

        # Check if event with this digest already exists
        existing_events = self.log.read_all()
        for event in existing_events:
            if (
                event.get("kind") == EventKinds.INTROSPECTION_QUERY
                and event.get("meta", {}).get("digest") == digest
            ):
                return event  # Return existing event, don't create duplicate

        event = {
            "kind": EventKinds.INTROSPECTION_QUERY,
            "content": kind,
            "meta": {"digest": digest, "payload": payload},
        }
        self.log.append(**event)
        return event
