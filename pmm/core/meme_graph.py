# Path: pmm/core/meme_graph.py
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
        meta = event.get("meta", {})

        # Add node
        self.graph.add_node(event_id, kind=kind)

        # Add edges
        if kind == "assistant_message":
            last_user = self._find_last("user_message")
            if last_user is not None:
                self.graph.add_edge(event_id, last_user, label="replies_to")
        elif kind == "commitment_open":
            # Link open → assistant_message that emitted a matching COMMIT line by meta.text
            text = (meta or {}).get("text")
            if isinstance(text, str) and text:
                assistant_node = self._find_assistant_with_commit_text(text)
                if assistant_node is not None:
                    self.graph.add_edge(event_id, assistant_node, label="commits_to")
        elif kind == "commitment_close":
            # Link this close event to its corresponding open event by cid
            cid = (meta or {}).get("cid")
            if isinstance(cid, str) and cid:
                open_node = self._find_commitment_open_by_cid(cid)
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

    def _find_assistant_with_commit_text(self, text: str) -> int | None:
        target = (text or "").strip()
        for node in self.graph.nodes:
            if self.graph.nodes[node]["kind"] == "assistant_message":
                full_event = self.eventlog.get(node)
                content = full_event.get("content", "")
                for line in content.splitlines():
                    if line.startswith("COMMIT:"):
                        remainder = line.split("COMMIT:", 1)[1].strip()
                        if remainder == target:
                            return node
        return None

    def _find_commitment_open_by_cid(self, cid: str) -> int | None:
        for node in self.graph.nodes:
            if self.graph.nodes[node]["kind"] == "commitment_open":
                full_event = self.eventlog.get(node)
                meta = full_event.get("meta", {})
                if meta.get("cid") == cid:
                    return node
        return None
