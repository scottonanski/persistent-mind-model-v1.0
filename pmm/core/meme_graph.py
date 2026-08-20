# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/core/meme_graph.py
"""MemeGraph projection for causal relationships over EventLog.

Append-only directed graph using NetworkX DiGraph.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
import threading
import networkx as nx
from typing import Dict, List, Iterable, Literal, Optional, Set

from .event_log import EventLog, TERMINAL_OUTCOME_PROTOCOL

OriginAttribution = Literal[
    "explicit",
    "legacy_inferred",
    "absent",
    "invalid_explicit",
]


@dataclass(frozen=True)
class CommitmentOrigin:
    """One episode origin and how that relationship was established."""

    event_id: int | None
    attribution: OriginAttribution


@dataclass(frozen=True)
class CommitmentClosure:
    """One close event and its assistant-command provenance, if established."""

    event_id: int
    origin: CommitmentOrigin


@dataclass(frozen=True)
class CommitmentEpisode:
    """One bounded open-to-close episode for a stable commitment CID."""

    cid: str
    open_event_id: int
    opening_origin: CommitmentOrigin
    closures: tuple[CommitmentClosure, ...]
    reflection_event_ids: tuple[int, ...]
    event_ids: tuple[int, ...]
    chronological_event_ids: tuple[int, ...]
    status: Literal["open", "closed"]


class MemeGraph:
    TRACKED_KINDS = {
        "user_message",
        "assistant_message",
        "commitment_open",
        "commitment_close",
        "identity_adoption",
        "reflection",
        "summary_update",
    }

    def __init__(self, eventlog: EventLog) -> None:
        self.eventlog = eventlog
        self.graph = nx.DiGraph()
        self._lock = threading.RLock()
        self._managed_assistant_ids: list[int] = []
        self._managed_pair_by_assistant: dict[int, int] = {}

    def rebuild(self, events: List[Dict]) -> None:
        with self._lock:
            self.graph.clear()
            self._managed_assistant_ids.clear()
            self._managed_pair_by_assistant.clear()
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
        self.graph.add_node(
            event_id,
            kind=kind,
            turn_protocol=(meta or {}).get("turn_protocol"),
        )

        # Add edges
        if kind == "assistant_message":
            if (meta or {}).get("turn_protocol") == TERMINAL_OUTCOME_PROTOCOL:
                about_event = (meta or {}).get("about_event")
                if self._is_prior_user_node(about_event, assistant_id=event_id):
                    user_id = int(about_event)
                    self.graph.add_edge(event_id, user_id, label="replies_to")
                    if (
                        self.graph.nodes[user_id].get("turn_protocol")
                        == TERMINAL_OUTCOME_PROTOCOL
                    ):
                        self._index_managed_pair(event_id, user_id)
            else:
                # Legacy assistant events have no mandatory canonical turn link.
                # Preserve the historical latest-user heuristic for graph shape,
                # but never promote those inferred pairs into the managed index.
                last_user = self._find_last("user_message")
                if last_user is not None:
                    self.graph.add_edge(event_id, last_user, label="replies_to")
        elif kind == "identity_adoption":
            # Link identity adoption to the most recent assistant_message or
            # reflection to form explicit identity threads.
            anchor = self._find_last_of_kinds(("assistant_message", "reflection"))
            if anchor is not None:
                self.graph.add_edge(event_id, anchor, label="adopts_identity_for")
        elif kind == "commitment_open":
            # New RuntimeLoop opens identify their exact producing assistant.
            # Older rows lack that field and retain the historical fallback.
            text = (meta or {}).get("text")
            if "origin_event_id" in (meta or {}):
                assistant_node = self._validated_commitment_origin(
                    opening_id=event_id,
                    origin_event_id=(meta or {}).get("origin_event_id"),
                    text=text,
                )
                if assistant_node is not None:
                    self.graph.add_edge(event_id, assistant_node, label="commits_to")
            elif isinstance(text, str) and text:
                assistant_node = self._find_assistant_with_commit_text(
                    text,
                    before_event_id=event_id,
                )
                if assistant_node is not None:
                    self.graph.add_edge(event_id, assistant_node, label="commits_to")
        elif kind == "commitment_close":
            # New authoritative closes identify the exact open event. Retain
            # CID lookup only for replaying legacy history.
            open_node = (meta or {}).get("open_event_id")
            valid_explicit_open = (
                isinstance(open_node, int)
                and not isinstance(open_node, bool)
                and self.graph.has_node(open_node)
                and self.graph.nodes[open_node].get("kind") == "commitment_open"
            )
            if not valid_explicit_open and "open_event_id" not in (meta or {}):
                cid = (meta or {}).get("cid")
                open_node = (
                    self._find_commitment_open_by_cid(cid)
                    if isinstance(cid, str) and cid
                    else None
                )
            elif not valid_explicit_open:
                open_node = None
            if open_node is not None:
                self.graph.add_edge(event_id, open_node, label="closes")
            if "origin_event_id" in (meta or {}):
                assistant_node = self._validated_commitment_close_origin(
                    closing_id=event_id,
                    open_event_id=open_node,
                    origin_event_id=(meta or {}).get("origin_event_id"),
                    cid=(meta or {}).get("cid"),
                )
                if assistant_node is not None:
                    self.graph.add_edge(event_id, assistant_node, label="issued_by")
        elif kind == "reflection":
            about_event = meta.get("about_event")
            if about_event and self.graph.has_node(about_event):
                self.graph.add_edge(event_id, about_event, label="reflects_on")

    def _is_prior_user_node(self, event_id: object, *, assistant_id: int) -> bool:
        return (
            isinstance(event_id, int)
            and not isinstance(event_id, bool)
            and event_id < assistant_id
            and self.graph.has_node(event_id)
            and self.graph.nodes[event_id].get("kind") == "user_message"
        )

    def _index_managed_pair(self, assistant_id: int, user_id: int) -> None:
        if assistant_id in self._managed_pair_by_assistant:
            return

        self._managed_pair_by_assistant[assistant_id] = user_id
        if (
            not self._managed_assistant_ids
            or assistant_id > self._managed_assistant_ids[-1]
        ):
            self._managed_assistant_ids.append(assistant_id)
            return

        position = bisect_left(self._managed_assistant_ids, assistant_id)
        self._managed_assistant_ids.insert(position, assistant_id)

    def prior_managed_pair(self, current_user_id: int) -> tuple[int, int] | None:
        """Return ``(user_id, assistant_id)`` for the prior managed turn.

        Selection is an indexed structural lookup. It does not traverse graph
        nodes or query canonical event content.
        """

        if (
            not isinstance(current_user_id, int)
            or isinstance(current_user_id, bool)
            or current_user_id <= 0
        ):
            raise ValueError("current_user_id must be a positive integer")

        with self._lock:
            position = bisect_left(self._managed_assistant_ids, current_user_id) - 1
            if position < 0:
                return None
            assistant_id = self._managed_assistant_ids[position]
            return self._managed_pair_by_assistant[assistant_id], assistant_id

    def _find_last(self, kind: str) -> int | None:
        candidates = [
            n for n in self.graph.nodes if self.graph.nodes[n]["kind"] == kind
        ]
        return max(candidates) if candidates else None

    def _find_last_of_kinds(self, kinds: Iterable[str]) -> int | None:
        """Return the most recent node id whose kind is in kinds, if any."""
        kind_set = {str(k) for k in kinds}
        candidates = [
            n for n in self.graph.nodes if self.graph.nodes[n].get("kind") in kind_set
        ]
        return max(candidates) if candidates else None

    def _find_node_with_content(self, kind: str, substring: str) -> int | None:
        for node in self.graph.nodes:
            if self.graph.nodes[node]["kind"] == kind:
                full_event = self.eventlog.get(node)
                if substring in full_event.get("content", ""):
                    return node
        return None

    def _find_assistant_with_commit_text(
        self,
        text: str,
        *,
        before_event_id: int,
    ) -> int | None:
        """Infer the latest prior matching assistant for a legacy open."""
        target = (text or "").strip()
        from pmm.core.semantic_extractor import extract_commitments

        for node in sorted(self.graph.nodes, reverse=True):
            if int(node) >= before_event_id:
                continue
            if self.graph.nodes[node]["kind"] == "assistant_message":
                full_event = self.eventlog.get(node)
                content = full_event.get("content", "")
                commitments = extract_commitments(content.splitlines())
                if target in commitments:
                    return node
        return None

    def _validated_commitment_origin(
        self,
        *,
        opening_id: int,
        origin_event_id: object,
        text: object,
    ) -> int | None:
        """Resolve an explicit, prior assistant that emitted this COMMIT line."""
        if (
            not isinstance(origin_event_id, int)
            or isinstance(origin_event_id, bool)
            or origin_event_id <= 0
            or origin_event_id >= opening_id
            or not self.graph.has_node(origin_event_id)
            or self.graph.nodes[origin_event_id].get("kind") != "assistant_message"
            or not isinstance(text, str)
            or not text.strip()
        ):
            return None

        from pmm.core.semantic_extractor import extract_commitments

        assistant = self.eventlog.get(origin_event_id) or {}
        commitments = extract_commitments(
            str(assistant.get("content") or "").splitlines()
        )
        return origin_event_id if text.strip() in commitments else None

    def _validated_commitment_close_origin(
        self,
        *,
        closing_id: int,
        open_event_id: object,
        origin_event_id: object,
        cid: object,
    ) -> int | None:
        """Resolve a closing assistant that emitted CLOSE for this episode."""
        if (
            not isinstance(open_event_id, int)
            or isinstance(open_event_id, bool)
            or not isinstance(origin_event_id, int)
            or isinstance(origin_event_id, bool)
            or not isinstance(cid, str)
            or not cid.strip()
            or origin_event_id >= closing_id
            or not self.graph.has_node(origin_event_id)
            or self.graph.nodes[origin_event_id].get("kind") != "assistant_message"
        ):
            return None

        if origin_event_id <= open_event_id:
            open_event = self.eventlog.get(open_event_id) or {}
            if (open_event.get("meta") or {}).get("origin_event_id") != origin_event_id:
                return None

        from pmm.core.semantic_extractor import extract_closures

        assistant = self.eventlog.get(origin_event_id) or {}
        closures = extract_closures(str(assistant.get("content") or "").splitlines())
        return origin_event_id if cid.strip() in closures else None

    def _find_commitment_open_by_cid(self, cid: str) -> int | None:
        """Return the greatest commitment_open node id recorded for a cid.

        Legacy ledgers may hold several opens for one cid. Resolving the
        greatest id selects the latest open, which is the one the authoritative
        close path transitions from and the one Mirror projects as open.
        """
        latest: int | None = None
        for node in self.graph.nodes:
            if self.graph.nodes[node]["kind"] == "commitment_open":
                full_event = self.eventlog.get(node)
                meta = full_event.get("meta", {})
                if meta.get("cid") == cid:
                    node_id = int(node)
                    if latest is None or node_id > latest:
                        latest = node_id
        return latest

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

    @staticmethod
    def _episode_origin(
        *,
        meta: Dict,
        related_event_ids: Iterable[int],
        allow_legacy_inference: bool,
    ) -> CommitmentOrigin:
        """Classify an origin without promoting malformed explicit metadata."""
        related = sorted({int(event_id) for event_id in related_event_ids})
        if "origin_event_id" in meta:
            declared = meta.get("origin_event_id")
            if (
                isinstance(declared, int)
                and not isinstance(declared, bool)
                and declared in related
            ):
                return CommitmentOrigin(declared, "explicit")
            return CommitmentOrigin(None, "invalid_explicit")
        if allow_legacy_inference and related:
            return CommitmentOrigin(related[0], "legacy_inferred")
        return CommitmentOrigin(None, "absent")

    def _episode_for_open_locked(self, open_event_id: int) -> CommitmentEpisode | None:
        if (
            not isinstance(open_event_id, int)
            or isinstance(open_event_id, bool)
            or open_event_id <= 0
            or not self.graph.has_node(open_event_id)
            or self.graph.nodes[open_event_id].get("kind") != "commitment_open"
        ):
            return None

        open_event = self.eventlog.get(open_event_id) or {}
        open_meta = open_event.get("meta") or {}
        cid = open_meta.get("cid")
        if not isinstance(cid, str) or not cid.strip():
            return None
        cid = cid.strip()

        opening_assistant_ids: list[int] = []
        for successor in self.graph.successors(open_event_id):
            edge = self.graph.get_edge_data(open_event_id, successor)
            if (edge or {}).get("label") == "commits_to":
                opening_assistant_ids.append(int(successor))
        opening_assistant_ids.sort()
        opening_origin = self._episode_origin(
            meta=open_meta,
            related_event_ids=opening_assistant_ids,
            allow_legacy_inference=True,
        )

        close_event_ids: list[int] = []
        for predecessor in self.graph.predecessors(open_event_id):
            edge = self.graph.get_edge_data(predecessor, open_event_id)
            if (edge or {}).get("label") == "closes":
                close_event_ids.append(int(predecessor))
        close_event_ids.sort()

        closures: list[CommitmentClosure] = []
        closing_assistant_ids: list[int] = []
        for close_event_id in close_event_ids:
            close_event = self.eventlog.get(close_event_id) or {}
            close_meta = close_event.get("meta") or {}
            issued_by_ids: list[int] = []
            for successor in self.graph.successors(close_event_id):
                edge = self.graph.get_edge_data(close_event_id, successor)
                if (edge or {}).get("label") == "issued_by":
                    issued_by_ids.append(int(successor))
            issued_by_ids.sort()
            closing_assistant_ids.extend(issued_by_ids)
            closures.append(
                CommitmentClosure(
                    event_id=close_event_id,
                    origin=self._episode_origin(
                        meta=close_meta,
                        related_event_ids=issued_by_ids,
                        allow_legacy_inference=False,
                    ),
                )
            )

        closing_thread_assistant_ids = sorted(
            set(closing_assistant_ids) - set(opening_assistant_ids)
        )
        all_assistant_ids = sorted(
            set(opening_assistant_ids).union(closing_assistant_ids)
        )
        reflection_event_ids: list[int] = []
        for assistant_id in all_assistant_ids:
            for predecessor in self.graph.predecessors(assistant_id):
                edge = self.graph.get_edge_data(predecessor, assistant_id)
                if (edge or {}).get("label") == "reflects_on":
                    reflection_event_ids.append(int(predecessor))
        reflection_event_ids = sorted(set(reflection_event_ids))

        event_ids = tuple(
            opening_assistant_ids
            + [open_event_id]
            + closing_thread_assistant_ids
            + close_event_ids
            + reflection_event_ids
        )
        return CommitmentEpisode(
            cid=cid,
            open_event_id=open_event_id,
            opening_origin=opening_origin,
            closures=tuple(closures),
            reflection_event_ids=tuple(reflection_event_ids),
            event_ids=event_ids,
            chronological_event_ids=tuple(sorted(set(event_ids))),
            status="closed" if closures else "open",
        )

    def episode_for_open(self, open_event_id: int) -> CommitmentEpisode | None:
        """Return one exact episode anchored by ``open_event_id``.

        Only validated graph relationships are promoted into the episode.
        Explicit malformed provenance is reported as ``invalid_explicit`` and
        never replaced with a heuristic relationship.
        """
        with self._lock:
            return self._episode_for_open_locked(open_event_id)

    def history_for_cid(self, cid: str) -> list[CommitmentEpisode]:
        """Return all reconstructed episodes for ``cid`` in open-event order."""
        cid = (cid or "").strip()
        if not cid:
            return []
        with self._lock:
            open_event_ids: list[int] = []
            for node in self.graph.nodes:
                if self.graph.nodes[node].get("kind") != "commitment_open":
                    continue
                event = self.eventlog.get(int(node)) or {}
                if (event.get("meta") or {}).get("cid") == cid:
                    open_event_ids.append(int(node))

            episodes: list[CommitmentEpisode] = []
            for open_event_id in sorted(open_event_ids):
                episode = self._episode_for_open_locked(open_event_id)
                if episode is not None:
                    episodes.append(episode)
            return episodes

    def current_episode_for_cid(self, cid: str) -> CommitmentEpisode | None:
        """Return the latest episode for ``cid`` without flattening history."""
        cid = (cid or "").strip()
        if not cid:
            return None
        with self._lock:
            open_event_id = self._find_commitment_open_by_cid(cid)
            if open_event_id is None:
                return None
            return self._episode_for_open_locked(open_event_id)

    def episodes_for_event(self, event_id: int) -> list[CommitmentEpisode]:
        """Return exact commitment episodes containing ``event_id``.

        An assistant message can legitimately originate commitments for more
        than one CID, so the result is plural and ordered by open event ID.
        """
        if not isinstance(event_id, int) or isinstance(event_id, bool) or event_id <= 0:
            return []
        with self._lock:
            if not self.graph.has_node(event_id):
                return []
            episodes: list[CommitmentEpisode] = []
            for cid in self.cids_for_event(event_id):
                for episode in self.history_for_cid(cid):
                    if event_id in episode.event_ids:
                        episodes.append(episode)
            episodes.sort(key=lambda episode: episode.open_event_id)
            return episodes

    def thread_for_cid(self, cid: str) -> list[int]:
        """Compatibility view of the current episode's semantic event order.

        Order: assistant_message (that issued COMMIT) -> commitment_open ->
        assistant_message (that issued CLOSE, when recorded) ->
        commitment_close (if any, possibly multiple) -> reflections that
        reflect on either assistant_message. All ids are stable within each
        category.
        """
        episode = self.current_episode_for_cid(cid)
        return list(episode.event_ids) if episode is not None else []

    def get_thread_slice(self, cid: str, *, limit: int = 12) -> List[int]:
        """Return a deterministic slice of a thread, capped by limit.

        Ordering within slice (deterministic):
        1) event_id descending
        2) kind ascending
        3) cid ascending (for stability when shared ids are present)
        """
        limit = max(1, int(limit))
        cid = (cid or "").strip()
        if not cid:
            return []
        full_thread = self.thread_for_cid(cid)
        if not full_thread:
            return []

        def _sort_key(eid: int) -> tuple:
            ev = self.eventlog.get(eid) or {}
            return (-int(eid), str(ev.get("kind") or ""), cid)

        ordered = sorted((int(eid) for eid in full_thread), key=_sort_key)
        return ordered[:limit]

    def cids_for_event(self, event_id: int) -> List[str]:
        """Return stable list of CIDs that this event participates in.

        Logic:
        - commitment_open/close: direct meta.cid
        - assistant_message: use opens/closes that identify it as their origin
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
                # Find lifecycle events that identify this assistant as origin.
                for pred in self.graph.predecessors(event_id):
                    edge = self.graph.get_edge_data(pred, event_id)
                    if (edge or {}).get("label") in {"commits_to", "issued_by"}:
                        lifecycle_event = self.eventlog.get(pred)
                        cid = (lifecycle_event.get("meta") or {}).get("cid")
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
                            if (edge_pos or {}).get("label") in {
                                "commits_to",
                                "issued_by",
                            }:
                                lifecycle_event = self.eventlog.get(pred_of_succ)
                                cid = (lifecycle_event.get("meta") or {}).get("cid")
                                if cid:
                                    cids.add(cid)

            return sorted(cids)

    def cids_containing_event(self, event_id: int) -> List[str]:
        """Return all CIDs whose threads include the event_id (deterministic)."""
        with self._lock:
            # Shortcut via direct mapping first
            direct = self.cids_for_event(event_id)
            if direct:
                return direct
            # Fallback scan over known opens (bounded by graph size)
            cids: Set[str] = set()
            for node in self.graph.nodes:
                node_kind = self.graph.nodes[node].get("kind")
                if node_kind != "commitment_open":
                    continue
                open_event = self.eventlog.get(int(node)) or {}
                cid_val = (open_event.get("meta") or {}).get("cid")
                if not cid_val:
                    continue
                if event_id in self.thread_for_cid(cid_val):
                    cids.add(cid_val)
            return sorted(cids)
