# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/core/meme_graph.py
"""MemeGraph projection for causal relationships over EventLog.

Append-only directed graph using NetworkX DiGraph.
"""

from __future__ import annotations

import threading
import networkx as nx
from typing import Dict, List, Iterable, Literal, Optional, Set

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
        self._lock = threading.RLock()

    def rebuild(self, events: List[Dict]) -> None:
        with self._lock:
            self.graph.clear()
            for event in events:
                self._add_event(event)

    def add_event(self, event: Dict) -> None:
        with self._lock:
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
        from pmm.core.semantic_extractor import extract_commitments

        for node in self.graph.nodes:
            if self.graph.nodes[node]["kind"] == "assistant_message":
                full_event = self.eventlog.get(node)
                content = full_event.get("content", "")
                commitments = extract_commitments(content.splitlines())
                if target in commitments:
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

    # Read-only helpers (deterministic, rebuildable)
    def graph_stats(self) -> dict:
        with self._lock:
            kinds: dict[str, int] = {}
            for node in self.graph.nodes:
                kind = self.graph.nodes[node].get("kind")
                if kind:
                    kinds[kind] = kinds.get(kind, 0) + 1
            return {
                "nodes": int(self.graph.number_of_nodes()),
                "edges": int(self.graph.number_of_edges()),
                "counts_by_kind": kinds,
            }

    def neighbors(
        self,
        event_id: int,
        *,
        direction: Literal["in", "out", "both"] = "both",
        kind: Optional[str] = None,
    ) -> List[int]:
        """Return deterministic neighbor ids for an event.

        - direction: "in", "out", or "both"
        - kind: optional filter on neighbor node kind
        """
        with self._lock:
            if not self.graph.has_node(event_id):
                return []

            neigh: Set[int] = set()
            if direction in ("out", "both"):
                for succ in self.graph.successors(event_id):
                    neigh.add(int(succ))
            if direction in ("in", "both"):
                for pred in self.graph.predecessors(event_id):
                    neigh.add(int(pred))

            if kind is not None:
                neigh = {n for n in neigh if self.graph.nodes[n].get("kind") == kind}

            return sorted(neigh)

    def subgraph_for_cid(self, cid: str) -> List[int]:
        """Return a stable list of event ids forming the commitment subgraph.

        Includes:
        - the canonical thread_for_cid() events
        - direct neighbors (both directions) of those events
        """
        cid = (cid or "").strip()
        if not cid:
            return []
        with self._lock:
            base = self.thread_for_cid(cid)
            if not base:
                return []

            included: Set[int] = set(int(eid) for eid in base)
            for eid in base:
                for n in self.neighbors(eid, direction="both"):
                    included.add(int(n))

            return sorted(included)

    def recent_frontier(
        self,
        *,
        limit: int = 32,
        kinds: Optional[Iterable[str]] = None,
    ) -> List[int]:
        """Return a deterministic 'frontier' of recent, structurally relevant nodes.

        Selection is purely ledger-ordered:
        - start from highest event id
        - optionally filter by node kind
        - keep up to `limit` nodes
        """
        limit = max(1, int(limit))
        if kinds is not None:
            kind_set = {str(k) for k in kinds}
        else:
            kind_set = None

        with self._lock:
            candidates: List[int] = []
            # Nodes correspond 1:1 with ledger ids, so sort numerically.
            for nid in sorted(self.graph.nodes, reverse=True):
                if kind_set is not None:
                    k = self.graph.nodes[nid].get("kind")
                    if k not in kind_set:
                        continue
                candidates.append(int(nid))
                if len(candidates) == limit:
                    break
            return sorted(candidates)

    def thread_for_cid(self, cid: str) -> list[int]:
        """Return ordered event ids forming the thread for a commitment cid.

        Order: assistant_message (that issued COMMIT) -> commitment_open ->
        commitment_close (if any, possibly multiple) -> reflections that
        reflect on the assistant_message. All ids sorted ascending within
        each category to keep stable ordering.
        """
        cid = (cid or "").strip()
        if not cid:
            return []
        with self._lock:
            open_node = self._find_commitment_open_by_cid(cid)
            if open_node is None:
                return []

            # assistant that triggered this open (edge label commits_to from open -> assistant)
            assistant_nodes: list[int] = []
            for succ in self.graph.successors(open_node):
                edge = self.graph.get_edge_data(open_node, succ)
                if (edge or {}).get("label") == "commits_to":
                    assistant_nodes.append(int(succ))
            assistant_nodes.sort()

            # closes pointing to this open (edge label closes from close -> open)
            close_nodes: list[int] = []
            for pred in self.graph.predecessors(open_node):
                edge = self.graph.get_edge_data(pred, open_node)
                if (edge or {}).get("label") == "closes":
                    close_nodes.append(int(pred))
            close_nodes.sort()

            # reflections that reflect on the assistant
            reflection_nodes: list[int] = []
            for an in assistant_nodes:
                for pred in self.graph.predecessors(an):
                    edge = self.graph.get_edge_data(pred, an)
                    if (edge or {}).get("label") == "reflects_on":
                        reflection_nodes.append(int(pred))
            reflection_nodes = sorted(set(reflection_nodes))

            ordered: list[int] = []
            ordered.extend(assistant_nodes)
            ordered.append(int(open_node))
            ordered.extend(close_nodes)
            ordered.extend(reflection_nodes)
            return ordered

    def cids_for_event(self, event_id: int) -> List[str]:
        """Return stable list of CIDs that this event participates in.

        Logic:
        - commitment_open/close: direct meta.cid
        - assistant_message: if an open points to it via commits_to, use that open's cid
        - reflection: if it points to an assistant via reflects_on, use that assistant's cids
        """
        with self._lock:
            if not self.graph.has_node(event_id):
                return []

            node = self.graph.nodes[event_id]
            kind = node.get("kind")
            full_event = self.eventlog.get(event_id)
            meta = full_event.get("meta", {})
            cids: Set[str] = set()

            if kind in ("commitment_open", "commitment_close"):
                cid = meta.get("cid")
                if cid:
                    cids.add(cid)

            elif kind == "assistant_message":
                # Find opens that point to this assistant
                for pred in self.graph.predecessors(event_id):
                    edge = self.graph.get_edge_data(pred, event_id)
                    if (edge or {}).get("label") == "commits_to":
                        # pred is the open event
                        open_event = self.eventlog.get(pred)
                        cid = (open_event.get("meta") or {}).get("cid")
                        if cid:
                            cids.add(cid)

            elif kind == "reflection":
                # Find assistant it reflects on
                for succ in self.graph.successors(event_id):
                    edge = self.graph.get_edge_data(event_id, succ)
                    if (edge or {}).get("label") == "reflects_on":
                        # succ is the assistant
                        # Recursively get cids for that assistant
                        # (Manual recursion to avoid infinite loops, though graph is acyclic-ish here)
                        # We just duplicate the assistant logic for safety and clarity
                        for pred_of_succ in self.graph.predecessors(succ):
                            edge_pos = self.graph.get_edge_data(pred_of_succ, succ)
                            if (edge_pos or {}).get("label") == "commits_to":
                                open_event = self.eventlog.get(pred_of_succ)
                                cid = (open_event.get("meta") or {}).get("cid")
                                if cid:
                                    cids.add(cid)

            return sorted(cids)
