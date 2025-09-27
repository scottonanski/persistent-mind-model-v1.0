from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

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


def _digest(payload: Dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha1(canonical).hexdigest()


@dataclass(frozen=True)
class MemeNode:
    digest: str
    label: str
    attrs: Dict[str, Any]


@dataclass(frozen=True)
class MemeEdge:
    digest: str
    label: str
    src: str
    dst: str
    attrs: Dict[str, Any]


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
        self._nodes: Dict[str, MemeNode] = {}
        self._edges: Dict[str, MemeEdge] = {}
        self._event_index: Dict[int, str] = {}
        self._digest_to_event_id: Dict[str, int] = {}
        self._identity_index: Dict[str, str] = {}
        self._commitment_index: Dict[str, str] = {}
        self._latest_stage: tuple[int, str] | None = None
        self._stage_history: List[tuple[int, Optional[str], str]] = []
        self._commitment_state: Dict[str, Dict[str, Any]] = {}
        self._metrics: Dict[str, Any] = {
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

    @property
    def last_batch_metrics(self) -> Dict[str, Any]:
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

    def _on_event_appended(self, event: Dict[str, Any]) -> None:
        # Listener runs outside EventLog lock; guard with our own lock.
        self._process_events([event])

    def _process_events(self, events: Iterable[Dict[str, Any]]) -> None:
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
        rss_kb: Optional[int]
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

    def _index_event(self, event: Dict[str, Any]) -> None:
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

    def _ensure_event_node(self, event: Dict[str, Any]) -> str:
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

    def _handle_identity_adopt(self, event: Dict[str, Any], event_digest: str) -> None:
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

    def _handle_commitment(self, event: Dict[str, Any], event_digest: str) -> None:
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
            edge_attrs = {"reason": reason} if reason else {}
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

    def _handle_reflection(self, event: Dict[str, Any], event_digest: str) -> None:
        meta = event.get("meta") or {}
        rid = int(event.get("id") or 0)
        attrs = {
            "rid": rid,
            "tag": meta.get("tag"),
            "prompt": meta.get("prompt_template"),
        }
        refl_digest = self._ensure_node("reflection", attrs)
        self._ensure_edge("captures", event_digest, refl_digest, {})

    def _handle_policy(self, event: Dict[str, Any], event_digest: str) -> None:
        meta = event.get("meta") or {}
        component = meta.get("component") or "unknown"
        attrs = {"component": component, "stage": meta.get("stage")}
        policy_digest = self._ensure_node("policy", attrs)
        self._ensure_edge("updates", event_digest, policy_digest, {})

    def _handle_stage(self, event: Dict[str, Any], event_digest: str) -> None:
        meta = event.get("meta") or {}
        stage_to = str(meta.get("to") or "")
        if not stage_to:
            return
        stage_from = str(meta.get("from") or "")
        try:
            eid = int(event.get("id") or 0)
        except Exception:
            eid = 0
        dst_digest = self._ensure_node("stage", {"name": stage_to})
        self._ensure_edge("advances_to", event_digest, dst_digest, {})
        if stage_from:
            src_digest = self._ensure_node("stage", {"name": stage_from})
            self._ensure_edge(
                "transition", src_digest, dst_digest, {"reason": meta.get("reason")}
            )
        if eid > 0:
            with self._lock:
                self._latest_stage = (eid, stage_to)
                self._stage_history.append((eid, stage_from or None, stage_to))

    def _handle_bandit(self, event: Dict[str, Any], event_digest: str) -> None:
        meta = event.get("meta") or {}
        attrs = {"kind": event.get("kind"), "meta": _normalize(meta)}
        node_digest = self._ensure_node("bandit", attrs)
        self._ensure_edge("bandit_event", event_digest, node_digest, {})

    def _handle_source_edges(self, event: Dict[str, Any], event_digest: str) -> None:
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
        self._ensure_edge(label, src_digest, event_digest, {})

    def _ensure_node(
        self,
        label: str,
        attrs: Dict[str, Any],
        *,
        index: Optional[Dict[str, str]] = None,
        index_key: Optional[str] = None,
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
        attrs: Dict[str, Any],
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

    def nodes_snapshot(self) -> Dict[str, MemeNode]:
        with self._lock:
            return dict(self._nodes)

    def edges_snapshot(self) -> Dict[str, MemeEdge]:
        with self._lock:
            return dict(self._edges)

    def latest_stage(self) -> Optional[str]:
        with self._lock:
            if self._latest_stage is None:
                return None
            return self._latest_stage[1]

    def stage_history(self) -> List[tuple[int, Optional[str], str]]:
        with self._lock:
            return list(self._stage_history)

    def open_commitments_snapshot(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            result: Dict[str, Dict[str, Any]] = {}
            for cid, data in self._commitment_state.items():
                if data.get("open"):
                    result[cid] = {
                        "text": data.get("text", ""),
                        "digest": data.get("digest"),
                        "last_event_id": data.get("last_event_id"),
                    }
            return result

    def policy_updates_for_reflection(self, ref_event_id: int) -> List[int]:
        with self._lock:
            digest = self._event_index.get(ref_event_id)
            if not digest:
                return []
            result: List[int] = []
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
        exclude_labels: Optional[set[str]] = None,
        recent_digest_blocklist: Optional[set[str]] = None,
    ) -> List[dict]:
        """Return a small list of high-confidence relations relevant to `topic`.

        Each relation is shaped as {"src_label", "src_event_id", "label", "dst_label", "dst_event_id"}.
        The heuristic is intentionally simple and deterministic: topic keywords are
        matched against node labels, and we prefer edges whose provenance stems
        from user/asserted content. Governance flavored labels (policy/stage/metric)
        can be excluded via `exclude_labels`.
        """

        topic = (topic or "").strip().lower()
        if not topic:
            return []

        exclude_labels = exclude_labels or set()
        recent_digest_blocklist = recent_digest_blocklist or set()

        with self._lock:
            scored: List[tuple[float, MemeNode, MemeEdge, MemeNode]] = []
            for edge in self._edges.values():
                if edge.label in exclude_labels:
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

                score = edge_conf + match_bonus
                scored.append((score, src, edge, dst))

            # Sort by descending score, deterministic tie-break by label text
            scored.sort(
                key=lambda tpl: (tpl[0], tpl[1].label or "", tpl[3].label or ""),
                reverse=True,
            )

            result: List[dict] = []
            for score, src, edge, dst in scored:
                if len(result) >= limit:
                    break
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
