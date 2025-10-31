from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from pmm.storage.eventlog import EventLog

logger = logging.getLogger("pmm.runtime.memegraph")


def _normalize(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {
            str(key): _normalize(val)
            for key, val in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple, set)):
        return [_normalize(item) for item in value]
    return str(value)


def _digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha1(canonical).hexdigest()


@dataclass(frozen=True)
class MemeNode:
    digest: str
    label: str
    attrs: dict[str, Any]


@dataclass(frozen=True)
class MemeEdge:
    digest: str
    label: str
    src: str
    dst: str
    attrs: dict[str, Any]


class MemeGraphProjection:
    """Graph-structured projection derived from the ledger mirror.

    Phase 1 focuses on deterministic node/edge construction without influencing
    runtime decision-making. Each append from EventLog triggers a lightweight
    update so that structural queries can be served from an O(Δ) cache rather
    than replaying the entire ledger.
    """

    def __init__(self, eventlog: EventLog) -> None:
        self.eventlog = eventlog
        self._lock = threading.RLock()
        self._nodes: dict[str, MemeNode] = {}
        self._edges: dict[str, MemeEdge] = {}
        self._event_index: dict[int, str] = {}
        self._digest_to_event_id: dict[str, int] = {}
        self._identity_index: dict[str, str] = {}
        self._commitment_index: dict[str, str] = {}
        self._stage_index: dict[str, str] = {}
        self._reflection_index: dict[int, str] = {}
        self._latest_stage: tuple[int, str] | None = None
        self._stage_history: list[tuple[int, str | None, str]] = []
        self._commitment_state: dict[str, dict[str, Any]] = {}
        self._metrics: dict[str, Any] = {
            "batch_events": 0,
            "duration_ms": 0.0,
            "nodes": 0,
            "edges": 0,
            "rss_kb": None,
        }

        try:
            events = eventlog.read_all()
        except Exception:
            events = []
        if events:
            self._process_events(events)
        eventlog.register_append_listener(self._on_event_appended)

    # ------------------------------------------------------------------ public

    @property
    def node_count(self) -> int:
        with self._lock:
            return len(self._nodes)

    @property
    def edge_count(self) -> int:
        with self._lock:
            return len(self._edges)

    def event_ids(self) -> list[int]:
        """Return all indexed event IDs in ascending order."""

        with self._lock:
            return sorted(self._event_index.keys())

    def open_commitment_cids(self) -> list[str]:
        """Return CIDs for commitments the graph currently tracks as open."""

        with self._lock:
            return [
                cid
                for cid, state in self._commitment_state.items()
                if state.get("open")
            ]

    def event_digest(self, event_id: int) -> str | None:
        """Return the event-node digest for a given ledger event id."""

        with self._lock:
            return self._event_index.get(int(event_id))

    def reflection_digest(self, reflection_id: int) -> str | None:
        """Return the reflection-node digest for a given reflection event id."""

        with self._lock:
            return self._reflection_index.get(int(reflection_id))

    def get_summary(self) -> str:
        """Return a compact human-readable summary of the graph structure."""
        with self._lock:
            node_count = len(self._nodes)
            edge_count = len(self._edges)

            # Count nodes by type
            node_types: dict[str, int] = {}
            for node in self._nodes.values():
                node_types[node.label] = node_types.get(node.label, 0) + 1

            # Get recent commitments
            open_commits = sum(
                1
                for state in self._commitment_state.values()
                if state.get("open", False)
            )

            # Format summary
            lines = [
                f"MemeGraph: {node_count} nodes, {edge_count} edges",
                f"Node types: {', '.join(f'{k}={v}' for k, v in sorted(node_types.items()))}",
                f"Open commitments tracked: {open_commits}",
            ]

            return " | ".join(lines)

    @property
    def last_batch_metrics(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._metrics)

    def rebuild(self) -> None:
        """Rebuild the projection from scratch using the current ledger."""
        try:
            events = self.eventlog.read_all()
        except Exception:
            events = []
        with self._lock:
            self._nodes.clear()
            self._edges.clear()
            self._event_index.clear()
            self._digest_to_event_id.clear()
            self._identity_index.clear()
            self._commitment_index.clear()
            self._latest_stage = None
            self._stage_history.clear()
            self._commitment_state.clear()
        if events:
            self._process_events(events)

    # --------------------------------------------------------------- internals

    def _on_event_appended(self, event: dict[str, Any]) -> None:
        # Listener runs outside EventLog lock; guard with our own lock.
        self._process_events([event])

    def _process_events(self, events: Iterable[dict[str, Any]]) -> None:
        start = time.perf_counter()
        batch = list(events)
        if not batch:
            return
        for event in batch:
            try:
                self._index_event(event)
            except Exception:
                logger.exception(
                    "MemeGraph failed processing event id=%s", event.get("id")
                )
        duration = time.perf_counter() - start
        self._record_metrics(len(batch), duration)

    def _record_metrics(self, batch_len: int, duration: float) -> None:
        rss_kb: int | None
        try:
            import resource

            rss_kb = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        except Exception:
            rss_kb = None
        metrics = {
            "batch_events": int(batch_len),
            "duration_ms": round(duration * 1000.0, 3),
            "nodes": self.node_count,
            "edges": self.edge_count,
            "rss_kb": rss_kb,
        }
        with self._lock:
            self._metrics = metrics
        logger.debug("MemeGraph batch processed: %s", metrics)

    # --------------------------------------------------------------- index ops

    def _index_event(self, event: dict[str, Any]) -> None:
        kind = str(event.get("kind") or "")
        if not kind:
            return
        event_digest = self._ensure_event_node(event)
        if kind == "identity_adopt":
            self._handle_identity_adopt(event, event_digest)
        elif kind in {"commitment_open", "commitment_close", "commitment_expire"}:
            self._handle_commitment(event, event_digest)
        elif kind == "reflection":
            self._handle_reflection(event, event_digest)
        elif kind == "policy_update":
            self._handle_policy(event, event_digest)
        elif kind == "stage_update":
            self._handle_stage(event, event_digest)
        elif kind in {"bandit_reward", "bandit_guidance_bias", "bandit_arm_chosen"}:
            self._handle_bandit(event, event_digest)
        # Always attempt to link metadata relationships shared across kinds.
        self._handle_source_edges(event, event_digest)

    def _ensure_event_node(self, event: dict[str, Any]) -> str:
        try:
            eid = int(event.get("id") or 0)
        except Exception:
            eid = 0
        payload = {"label": "event", "id": eid, "kind": str(event.get("kind") or "")}
        digest = _digest(payload)
        with self._lock:
            if digest not in self._nodes:
                node = MemeNode(digest=digest, label="event", attrs=payload)
                self._nodes[digest] = node
            if eid:
                self._event_index[eid] = digest
            if eid:
                self._digest_to_event_id[digest] = eid
        return digest

    def _handle_identity_adopt(self, event: dict[str, Any], event_digest: str) -> None:
        meta = event.get("meta") or {}
        identity_name = (
            meta.get("sanitized")
            or meta.get("name")
            or (event.get("content") or "").strip()
        )
        if not identity_name:
            return
        attrs = {"name": identity_name}
        identity_digest = self._ensure_node(
            "identity", attrs, index=self._identity_index
        )
        confidence = None
        try:
            confidence = (
                float(meta.get("confidence"))
                if meta.get("confidence") is not None
                else None
            )
        except Exception:
            confidence = None
        edge_attrs = {"confidence": confidence} if confidence is not None else {}
        self._ensure_edge("adopts", event_digest, identity_digest, edge_attrs)

    def _handle_commitment(self, event: dict[str, Any], event_digest: str) -> None:
        kind = str(event.get("kind") or "")
        meta = event.get("meta") or {}
        cid = str(meta.get("cid") or "")
        if not cid:
            return
        text = meta.get("text") or ""
        attrs = {"cid": cid, "text": text}
        commit_digest = self._ensure_node(
            "commitment", attrs, index=self._commitment_index, index_key=cid
        )
        edge_label = {
            "commitment_open": "opens",
            "commitment_close": "closes",
            "commitment_expire": "expires",
        }.get(kind)
        if edge_label:
            reason = meta.get("reason") or meta.get("source") or meta.get("state")
            edge_attrs = {
                "confidence": 0.85
            }  # High confidence for direct state changes
            if reason:
                edge_attrs["reason"] = reason
            self._ensure_edge(edge_label, event_digest, commit_digest, edge_attrs)
        try:
            eid = int(event.get("id") or 0)
        except Exception:
            eid = 0
        with self._lock:
            state = self._commitment_state.setdefault(
                cid,
                {
                    "digest": commit_digest,
                    "text": text,
                    "open": False,
                    "last_event_id": eid,
                },
            )
            if kind == "commitment_open":
                state.update(
                    {
                        "open": True,
                        "text": text,
                        "last_event_id": eid,
                        "last_event_kind": kind,
                    }
                )
            elif kind in {"commitment_close", "commitment_expire"}:
                state.update(
                    {
                        "open": False,
                        "last_event_id": eid,
                        "last_event_kind": kind,
                    }
                )

    def _handle_reflection(self, event: dict[str, Any], event_digest: str) -> None:
        meta = event.get("meta") or {}
        rid = int(event.get("id") or 0)
        attrs = {
            "rid": rid,
            "tag": meta.get("tag"),
            "prompt": meta.get("prompt_template"),
        }
        refl_digest = self._ensure_node("reflection", attrs)
        with self._lock:
            if rid:
                self._reflection_index[rid] = refl_digest
        self._ensure_edge(
            "captures", event_digest, refl_digest, {"confidence": 0.7}
        )  # Medium confidence for reasoning captures

    def _handle_policy(self, event: dict[str, Any], event_digest: str) -> None:
        meta = event.get("meta") or {}
        component = meta.get("component") or "unknown"
        attrs = {"component": component, "stage": meta.get("stage")}
        policy_digest = self._ensure_node("policy", attrs)
        self._ensure_edge(
            "updates", event_digest, policy_digest, {"confidence": 0.9}
        )  # Very high confidence for authoritative policies

    def _handle_stage(self, event: dict[str, Any], event_digest: str) -> None:
        meta = event.get("meta") or {}
        stage_to = str(meta.get("to") or "")
        if not stage_to:
            return
        stage_from = str(meta.get("from") or "")
        try:
            eid = int(event.get("id") or 0)
        except Exception:
            eid = 0
        dst_digest = self._ensure_node(
            "stage",
            {"name": stage_to},
            index=self._stage_index,
            index_key=stage_to,
        )
        self._ensure_edge(
            "advances_to", event_digest, dst_digest, {"confidence": 0.85}
        )  # High confidence for core state changes
        if stage_from:
            src_digest = self._ensure_node("stage", {"name": stage_from})
            self._ensure_edge(
                "transition",
                src_digest,
                dst_digest,
                {
                    "confidence": 0.85,
                    "reason": meta.get("reason"),
                },  # High confidence for core state changes
            )
        if eid > 0:
            with self._lock:
                self._latest_stage = (eid, stage_to)
                self._stage_history.append((eid, stage_from or None, stage_to))

    def _handle_bandit(self, event: dict[str, Any], event_digest: str) -> None:
        meta = event.get("meta") or {}
        attrs = {"kind": event.get("kind"), "meta": _normalize(meta)}
        node_digest = self._ensure_node("bandit", attrs)
        self._ensure_edge(
            "bandit_event", event_digest, node_digest, {"confidence": 0.7}
        )  # Medium confidence for experimental learning

    def _handle_source_edges(self, event: dict[str, Any], event_digest: str) -> None:
        meta = event.get("meta") or {}
        src_id = meta.get("src_id") or meta.get("source_event_id")
        if src_id is None:
            return
        try:
            src_id_int = int(src_id)
        except Exception:
            return
        with self._lock:
            src_digest = self._event_index.get(src_id_int)
        if not src_digest:
            return
        label = f"references:{str(event.get('kind'))}"
        self._ensure_edge(
            label, src_digest, event_digest, {"confidence": 0.65}
        )  # Lower confidence for indirect relationships

    def _ensure_node(
        self,
        label: str,
        attrs: dict[str, Any],
        *,
        index: dict[str, str] | None = None,
        index_key: str | None = None,
    ) -> str:
        normalized_attrs = _normalize(attrs)
        payload = {"label": label, "attrs": normalized_attrs}
        digest = _digest(payload)
        with self._lock:
            if digest not in self._nodes:
                node = MemeNode(digest=digest, label=label, attrs=normalized_attrs)
                self._nodes[digest] = node
            if index is not None:
                key = (
                    index_key
                    if index_key is not None
                    else str(
                        normalized_attrs.get("name") or normalized_attrs.get("cid")
                    )
                )
                if key:
                    index[key] = digest
        return digest

    def _ensure_edge(
        self,
        label: str,
        src: str,
        dst: str,
        attrs: dict[str, Any],
    ) -> str:
        normalized_attrs = _normalize(attrs)
        payload = {
            "label": label,
            "src": src,
            "dst": dst,
            "attrs": normalized_attrs,
        }
        digest = _digest(payload)
        with self._lock:
            if digest not in self._edges:
                edge = MemeEdge(
                    digest=digest,
                    label=label,
                    src=src,
                    dst=dst,
                    attrs=normalized_attrs,
                )
                self._edges[digest] = edge
        return digest

    # ----------------------------------------------------------------- utility

    def nodes_snapshot(self) -> dict[str, MemeNode]:
        with self._lock:
            return dict(self._nodes)

    def edges_snapshot(self) -> dict[str, MemeEdge]:
        with self._lock:
            return dict(self._edges)

    def latest_stage(self) -> str | None:
        with self._lock:
            if self._latest_stage is None:
                return None
            return self._latest_stage[1]

    def latest_stage_entry(self) -> dict[str, int | str | None] | None:
        """Return the most recent stage update with associated digests."""

        with self._lock:
            if self._latest_stage is None:
                return None
            eid, stage_to = self._latest_stage
            return {
                "event_id": eid,
                "stage": stage_to,
                "event_digest": self._event_index.get(eid),
                "stage_digest": self._stage_index.get(stage_to),
            }

    def stage_history(self) -> list[tuple[int, str | None, str]]:
        with self._lock:
            return list(self._stage_history)

    def stage_history_with_tokens(
        self, *, limit: int | None = None
    ) -> list[dict[str, int | str | None]]:
        """Return stage history entries annotated with memegraph digests."""

        with self._lock:
            history = (
                self._stage_history if limit is None else self._stage_history[-limit:]
            )
            result: list[dict[str, int | str | None]] = []
            for eid, stage_from, stage_to in history:
                result.append(
                    {
                        "event_id": eid,
                        "stage_from": stage_from,
                        "stage_to": stage_to,
                        "event_digest": self._event_index.get(eid),
                        "stage_digest": self._stage_index.get(stage_to),
                    }
                )
            return result

    def open_commitments_snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            result: dict[str, dict[str, Any]] = {}
            for cid, data in self._commitment_state.items():
                if data.get("open"):
                    result[cid] = {
                        "text": data.get("text", ""),
                        "digest": data.get("digest"),
                        "last_event_id": data.get("last_event_id"),
                    }
            return result

    def policy_updates_for_reflection(self, ref_event_id: int) -> list[int]:
        with self._lock:
            digest = self._event_index.get(ref_event_id)
            if not digest:
                return []
            result: list[int] = []
            for edge in self._edges.values():
                if edge.src == digest and edge.label == "references:policy_update":
                    dst_id = self._digest_to_event_id.get(edge.dst)
                    if dst_id:
                        result.append(dst_id)
            return result

    # --- Graph slice exposure -------------------------------------------------

    def graph_slice(
        self,
        topic: str,
        *,
        limit: int = 3,
        min_confidence: float = 0.6,
        exclude_labels: set[str] | None = None,
        recent_digest_blocklist: set[str] | None = None,
        trace_buffer: Any | None = None,
    ) -> list[dict]:
        """Return a small list of high-confidence relations relevant to `topic`.

        Each relation is shaped as {"src_label", "src_event_id", "label", "dst_label", "dst_event_id"}.
        The heuristic is intentionally simple and deterministic: topic keywords are
        matched against node labels, and we prefer edges whose provenance stems
        from user/asserted content. Governance flavored labels (policy/stage/metric)
        can be excluded via `exclude_labels`.

        Args:
            topic: Query topic to search for
            limit: Maximum number of results
            min_confidence: Minimum confidence threshold
            exclude_labels: Labels to exclude from results
            recent_digest_blocklist: Digests to exclude
            trace_buffer: Optional TraceBuffer for reasoning trace logging
        """

        topic = (topic or "").strip().lower()
        if not topic:
            return []

        exclude_labels = exclude_labels or set()
        recent_digest_blocklist = recent_digest_blocklist or set()

        with self._lock:
            scored: list[tuple[float, MemeNode, MemeEdge, MemeNode]] = []
            traversal_depth = 0

            for edge in self._edges.values():
                # Governance-blind: filter governance-flavored relations
                elow = (edge.label or "").lower()
                if edge.label in exclude_labels or any(
                    tok in elow for tok in ("policy", "stage", "metric")
                ):
                    continue
                if (
                    edge.src in recent_digest_blocklist
                    or edge.dst in recent_digest_blocklist
                    or edge.digest in recent_digest_blocklist
                ):
                    continue
                edge_conf = float(edge.attrs.get("confidence", 0.5))
                if edge_conf < float(min_confidence):
                    continue

                src = self._nodes.get(edge.src)
                dst = self._nodes.get(edge.dst)
                if not src or not dst:
                    continue

                src_label = (src.label or "").lower()
                dst_label = (dst.label or "").lower()
                # Skip edges touching governance nodes outright
                if src_label in {"policy", "stage", "metrics"} or dst_label in {
                    "policy",
                    "stage",
                    "metrics",
                }:
                    continue

                traversal_depth += 1

                # Topic match heuristic: simple containment or token overlap
                match_bonus = 0.0
                if topic in src_label or topic in dst_label:
                    match_bonus = 0.4
                else:
                    topic_tokens = {t for t in topic.split() if t}
                    if topic_tokens and (
                        topic_tokens.intersection(src_label.split())
                        or topic_tokens.intersection(dst_label.split())
                    ):
                        match_bonus = 0.2

                if match_bonus == 0.0:
                    # Also consider edges tied to recent assertions (knowledge)
                    if "autonomy" in topic and "commitment" in src_label:
                        match_bonus = 0.1
                    elif "identity" in topic and (
                        "identity" in src_label or "name" in dst_label
                    ):
                        match_bonus = 0.1
                    elif "metaphor" in topic and "reflection" in src_label:
                        match_bonus = 0.1

                if match_bonus == 0.0:
                    continue

                # Provenance preference: bonus if tied to user/asserted/cross-validated
                prov_bonus = 0.0
                try:
                    # If either endpoint is an event with kind=user or knowledge_assert, prefer it
                    src_kind = (
                        (src.attrs or {}).get("kind") if src.label == "event" else None
                    )
                    dst_kind = (
                        (dst.attrs or {}).get("kind") if dst.label == "event" else None
                    )
                    if str(src_kind) in {"user", "knowledge_assert"} or str(
                        dst_kind
                    ) in {
                        "user",
                        "knowledge_assert",
                    }:
                        prov_bonus += 0.1
                except Exception:
                    pass
                score = edge_conf + match_bonus + prov_bonus
                scored.append((score, src, edge, dst))

            # Sort by descending score, deterministic tie-break by label text
            scored.sort(
                key=lambda tpl: (tpl[0], tpl[1].label or "", tpl[3].label or ""),
                reverse=True,
            )

            result: list[dict] = []
            for score, src, edge, dst in scored:
                if len(result) >= limit:
                    break
                if trace_buffer and not result:
                    trace_buffer.record_node_visit(
                        node_digest=src.digest,
                        node_type=src.label,
                        context_query=topic,
                        traversal_depth=0,
                        confidence=edge.attrs.get("confidence", 0.5),
                        edge_label=edge.label,
                        reasoning_step=f"Examining {src.label} node via {edge.label} edge",
                    )
                    trace_buffer.record_node_visit(
                        node_digest=dst.digest,
                        node_type=dst.label,
                        context_query=topic,
                        traversal_depth=1,
                        confidence=edge.attrs.get("confidence", 0.5),
                        edge_label=edge.label,
                        reasoning_step=f"Following {edge.label} to {dst.label} node",
                    )
                src_eid = self._digest_to_event_id.get(src.digest)
                dst_eid = self._digest_to_event_id.get(dst.digest)
                relation = {
                    "src": src.label,
                    "src_digest": src.digest,
                    "src_event_id": src_eid,
                    "label": edge.label,
                    "dst": dst.label,
                    "dst_digest": dst.digest,
                    "dst_event_id": dst_eid,
                    "score": round(score, 3),
                    "edge_digest": edge.digest,
                }
                result.append(relation)

            return result

    def compute_deltas_since(
        self, previous_snapshot: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Compute memegraph deltas since a previous snapshot.

        Returns a list of delta events that would have been emitted, without actually
        emitting them. This maintains ledger integrity while providing provenance.

        Args:
            previous_snapshot: Previous state from export_state()

        Returns:
            List of delta event dictionaries
        """
        deltas = []
        with self._lock:
            prev_nodes = previous_snapshot.get("nodes", {})
            prev_edges = previous_snapshot.get("edges", {})

            # Check for new nodes
            for digest, node_data in self._nodes.items():
                if digest not in prev_nodes:
                    deltas.append(
                        {
                            "kind": "memegraph_delta",
                            "content": "",
                            "meta": {
                                "operation": "node_created",
                                "node_digest": digest,
                                "node_label": node_data.label,
                                "node_attrs": node_data.attrs,
                                "total_nodes": len(self._nodes),
                                "total_edges": len(self._edges),
                            },
                        }
                    )

            # Check for new edges
            for digest, edge_data in self._edges.items():
                if digest not in prev_edges:
                    deltas.append(
                        {
                            "kind": "memegraph_delta",
                            "content": "",
                            "meta": {
                                "operation": "edge_created",
                                "edge_digest": digest,
                                "edge_label": edge_data.label,
                                "src_digest": edge_data.src,
                                "dst_digest": edge_data.dst,
                                "edge_attrs": edge_data.attrs,
                                "total_nodes": len(self._nodes),
                                "total_edges": len(self._edges),
                            },
                        }
                    )

        return deltas

    def export_state(self) -> dict[str, Any]:
        """Export MemeGraph state for snapshotting.

        Returns a serializable dict containing all graph state that can be
        restored later without replaying events.
        """
        with self._lock:
            # Convert nodes to serializable format
            nodes_data = {}
            for digest, node in self._nodes.items():
                nodes_data[digest] = {
                    "label": node.label,
                    "attrs": node.attrs,
                }

            # Convert edges to serializable format
            edges_data = {}
            for digest, edge in self._edges.items():
                edges_data[digest] = {
                    "label": edge.label,
                    "src": edge.src,
                    "dst": edge.dst,
                    "attrs": edge.attrs,
                }

            return {
                "nodes": nodes_data,
                "edges": edges_data,
                "event_index": self._event_index.copy(),
                "digest_to_event_id": self._digest_to_event_id.copy(),
                "identity_index": self._identity_index.copy(),
                "commitment_index": self._commitment_index.copy(),
                "latest_stage": self._latest_stage,
                "stage_history": self._stage_history.copy(),
                "commitment_state": self._commitment_state.copy(),
                "metrics": self._metrics.copy(),
            }

    def import_state(self, state: dict[str, Any]) -> None:
        """Import MemeGraph state from snapshot.

        Restores graph state without replaying events. Used when loading
        from a snapshot to avoid O(n) reconstruction.

        Args:
            state: State dict from export_state()
        """
        with self._lock:
            # Restore nodes
            self._nodes.clear()
            for digest, node_data in state.get("nodes", {}).items():
                self._nodes[digest] = MemeNode(
                    digest=digest,
                    label=node_data["label"],
                    attrs=node_data["attrs"],
                )

            # Restore edges
            self._edges.clear()
            for digest, edge_data in state.get("edges", {}).items():
                self._edges[digest] = MemeEdge(
                    digest=digest,
                    label=edge_data["label"],
                    src=edge_data["src"],
                    dst=edge_data["dst"],
                    attrs=edge_data["attrs"],
                )

            # Restore indexes
            self._event_index = state.get("event_index", {}).copy()
            self._digest_to_event_id = state.get("digest_to_event_id", {}).copy()
            self._identity_index = state.get("identity_index", {}).copy()
            self._commitment_index = state.get("commitment_index", {}).copy()
            self._latest_stage = state.get("latest_stage")
            self._stage_history = state.get("stage_history", []).copy()
            self._commitment_state = state.get("commitment_state", {}).copy()
            self._metrics = state.get(
                "metrics",
                {
                    "batch_events": 0,
                    "duration_ms": 0.0,
                    "nodes": 0,
                    "edges": 0,
                    "rss_kb": None,
                },
            ).copy()

            # Update metrics to reflect current state
            self._metrics["nodes"] = len(self._nodes)
            self._metrics["edges"] = len(self._edges)
