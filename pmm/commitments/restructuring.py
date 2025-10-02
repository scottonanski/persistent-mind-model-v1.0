# pmm/commitments/restructuring.py

import hashlib
import json
from typing import Any

from pmm.constants import EventKinds
from pmm.storage.eventlog import EventLog


class CommitmentRestructurer:
    """Deterministic commitment restructuring with audit-safe event emission."""

    def __init__(self, log: EventLog):
        self.log = log

    def _get_open_commitments(self) -> list[dict[str, Any]]:
        """Get currently open commitments from the event log."""
        events = self.log.read_all()

        # Track commitment states
        commitment_states = {}
        for e in events:
            if e["kind"] == EventKinds.COMMITMENT_OPEN:
                cid = e.get("meta", {}).get("cid")
                if cid:
                    commitment_states[cid] = {
                        "cid": cid,
                        "text": e.get("meta", {}).get("text") or e.get("content", ""),
                        "priority": e.get("meta", {}).get("priority", 0.5),
                        "event_id": e["id"],
                        "status": "open",
                    }
            elif e["kind"] == EventKinds.COMMITMENT_CLOSE:
                cid = e.get("meta", {}).get("cid")
                if cid and cid in commitment_states:
                    commitment_states[cid]["status"] = "closed"

        # Return only open commitments
        return [c for c in commitment_states.values() if c["status"] == "open"]

    def _text_similarity(self, text1: str, text2: str) -> float:
        """Deterministic text similarity using simple token overlap."""
        from pmm.utils.parsers import token_overlap_ratio

        return token_overlap_ratio(text1, text2)

    # ----------------------------
    # Core restructuring operations
    # ----------------------------

    def consolidate_similar(self, threshold: float = 0.9) -> list[dict[str, Any]]:
        """
        Deterministically consolidate commitments that are near-duplicates.
        Example output: [{"op": "merge", "cids": ["c12", "c15"], "new_cid": "c99"}]
        """
        open_commitments = self._get_open_commitments()
        changes = []
        processed = set()

        for i, c1 in enumerate(open_commitments):
            if c1["cid"] in processed:
                continue

            similar_group = [c1["cid"]]

            for j, c2 in enumerate(open_commitments[i + 1 :], i + 1):
                if c2["cid"] in processed:
                    continue

                similarity = self._text_similarity(c1["text"], c2["text"])
                if similarity >= threshold:
                    similar_group.append(c2["cid"])
                    processed.add(c2["cid"])

            if len(similar_group) > 1:
                # Generate deterministic new cid
                sorted_cids = sorted(similar_group)
                new_cid = f"merged_{hashlib.sha256(''.join(sorted_cids).encode()).hexdigest()[:8]}"

                changes.append({"op": "merge", "cids": sorted_cids, "new_cid": new_cid})
                processed.update(similar_group)

        return changes

    def reprioritize_stale(self, age_threshold: int = 10) -> list[dict[str, Any]]:
        """
        Reprioritize commitments that have been open longer than age_threshold events.
        Example output: [{"op": "reprioritize", "cid": "c20", "priority": 0.45}]
        """
        open_commitments = self._get_open_commitments()
        all_events = self.log.read_all()
        changes = []

        for commitment in open_commitments:
            # Count events since this commitment was opened
            events_since_open = len(
                [e for e in all_events if e["id"] > commitment["event_id"]]
            )

            if events_since_open >= age_threshold:
                # Deterministic priority adjustment
                current_priority = commitment["priority"]
                new_priority = min(0.9, current_priority + 0.05)

                if new_priority != current_priority:
                    changes.append(
                        {
                            "op": "reprioritize",
                            "cid": commitment["cid"],
                            "old_priority": current_priority,
                            "new_priority": new_priority,
                        }
                    )

        return changes

    def merge_redundant(
        self, similarity_threshold: float = 0.95
    ) -> list[dict[str, Any]]:
        """
        Merge commitments that are semantically redundant.
        Example output: [{"op": "merge", "cids": ["c7", "c9"], "new_cid": "c10"}]
        """
        # For now, this is the same as consolidate_similar with higher threshold
        return self.consolidate_similar(threshold=similarity_threshold)

    # ----------------------------
    # Event emission
    # ----------------------------

    def _digest_changes(self, changes: list[dict[str, Any]]) -> str:
        """Stable digest of change set for idempotency."""
        payload = json.dumps(changes, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def emit_restructuring_event(self, changes: list[dict[str, Any]]) -> int | None:
        """
        Emit EventKinds.EVOLUTION event if changes exist.
        Idempotent via digest; returns event ID or None.
        """
        if not changes:
            return None

        digest = self._digest_changes(changes)

        # Check for existing events with same digest
        existing_events = [
            e
            for e in self.log.read_all()
            if e.get("kind") == EventKinds.EVOLUTION
            and e.get("meta", {}).get("digest") == digest
        ]

        if existing_events:
            return existing_events[0]["id"]

        return self.log.append(
            kind=EventKinds.EVOLUTION,
            content="",  # semantic meaning is in meta only
            meta={"digest": digest, "changes": changes},
        )

    # ----------------------------
    # Orchestration
    # ----------------------------

    def run_restructuring(self) -> int | None:
        """
        Execute all restructuring passes and emit a single event if changes exist.
        Deterministic, idempotent, and schema-safe.
        """
        changes: list[dict[str, Any]] = []
        changes.extend(self.consolidate_similar())
        changes.extend(self.reprioritize_stale())
        changes.extend(self.merge_redundant())

        return self.emit_restructuring_event(changes)
