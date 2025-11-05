"""MemeGraph projection for causal relationships over EventLog.

Append-only directed graph using NetworkX DiGraph.
"""

from __future__ import annotations

import networkx as nx
from typing import Dict, List

from .event_log import EventLog


class MemeGraph:
    TRACKED_KINDS = {
        "user_message",
        "assistant_message",
        "commitment_open",
        "commitment_close",
        "reflection",
        "summary_update",
    }

    def __init__(self, eventlog: EventLog) -> None:
        self.eventlog = eventlog
        self.graph = nx.DiGraph()

    def rebuild(self, events: List[Dict]) -> None:
        self.graph.clear()
        for event in events:
            self._add_event(event)

    def add_event(self, event: Dict) -> None:
        if self.graph.has_node(event["id"]):
            return
        if event["kind"] not in self.TRACKED_KINDS:
            return
        self._add_event(event)

    def _add_event(self, event: Dict) -> None:
        event_id = event["id"]
        kind = event["kind"]
        content = event.get("content", "")
        meta = event.get("meta", {})

        # Add node
        self.graph.add_node(event_id, kind=kind)

        # Add edges
        if kind == "assistant_message":
            last_user = self._find_last("user_message")
            if last_user is not None:
                self.graph.add_edge(event_id, last_user, label="replies_to")
        elif kind == "commitment_open":
            if "COMMIT:" in content:
                cid = content[7:]
                assistant_node = self._find_node_with_content(
                    "assistant_message", f"COMMIT:{cid}"
                )
                if assistant_node is not None:
                    self.graph.add_edge(event_id, assistant_node, label="commits_to")
        elif kind == "commitment_close":
            if "CLOSE:" in content:
                cid = content[6:]
                open_node = self._find_node_with_content(
                    "commitment_open", f"COMMIT:{cid}"
                )
                if open_node is not None:
                    self.graph.add_edge(event_id, open_node, label="closes")
        elif kind == "reflection":
            about_event = meta.get("about_event")
            if about_event and self.graph.has_node(about_event):
                self.graph.add_edge(event_id, about_event, label="reflects_on")

    def _find_last(self, kind: str) -> int | None:
        candidates = [
            n for n in self.graph.nodes if self.graph.nodes[n]["kind"] == kind
        ]
        return max(candidates) if candidates else None

    def _find_node_with_content(self, kind: str, substring: str) -> int | None:
        for node in self.graph.nodes:
            if self.graph.nodes[node]["kind"] == kind:
                full_event = self.eventlog.get(node)
                if substring in full_event.get("content", ""):
                    return node
        return None
