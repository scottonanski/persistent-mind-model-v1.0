"""Lightweight reasoning trace collection with sampling.

Captures PMM's reasoning process (node traversal, confidence levels, query context)
without performance degradation through:
- Probabilistic sampling (default 1% of node visits)
- Always-log high-confidence decisions (>0.8)
- Async batch writing to prevent blocking
- Session-based aggregation for coherent trace summaries
"""

from __future__ import annotations

import random
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger(__name__)


@dataclass
class TraceNode:
    """Single node visit in reasoning trace."""

    node_digest: str
    node_type: str
    context_query: str
    traversal_depth: int
    confidence: float
    timestamp_ms: int
    edge_label: Optional[str] = None
    reasoning_step: Optional[str] = None


@dataclass
class TraceSession:
    """Aggregated trace data for a single reasoning session."""

    session_id: str
    query: str
    start_time_ms: int
    end_time_ms: int = 0
    total_nodes_visited: int = 0
    node_type_distribution: Dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    high_confidence_nodes: List[Dict[str, Any]] = field(default_factory=list)
    sampled_nodes: List[TraceNode] = field(default_factory=list)
    reasoning_steps: List[str] = field(default_factory=list)


class TraceBuffer:
    """Non-blocking trace collection with probabilistic sampling.

    Design principles:
    - Minimal overhead: Single random() check for most node visits
    - High-value capture: Always log high-confidence decisions
    - Batch writes: Aggregate before writing to eventlog
    - Thread-safe: Lock-protected buffer operations
    """

    def __init__(
        self,
        sampling_rate: float = 0.01,
        min_confidence_always_log: float = 0.8,
        buffer_size: int = 1000,
    ):
        """Initialize trace buffer.

        Args:
            sampling_rate: Probability of logging a node visit (0.0-1.0)
            min_confidence_always_log: Confidence threshold for always logging
            buffer_size: Max samples before auto-flush warning
        """
        self.sampling_rate = float(sampling_rate)
        self.min_confidence_always_log = float(min_confidence_always_log)
        self.buffer_size = int(buffer_size)

        self._lock = threading.RLock()
        self._current_session: Optional[TraceSession] = None
        self._sessions: List[TraceSession] = []

    def start_session(self, query: str, session_id: Optional[str] = None) -> str:
        """Start a new reasoning trace session.

        Args:
            query: The query/context driving this reasoning session
            session_id: Optional explicit session ID (generates UUID if None)

        Returns:
            Session ID for this trace session
        """
        sid = session_id or str(uuid.uuid4())
        timestamp_ms = int(time.time() * 1000)

        with self._lock:
            # Finalize previous session if exists
            if self._current_session:
                self._finalize_current_session()

            self._current_session = TraceSession(
                session_id=sid,
                query=query,
                start_time_ms=timestamp_ms,
            )

        logger.debug(f"Started trace session {sid[:8]} for query: {query[:50]}")
        return sid

    def record_node_visit(
        self,
        node_digest: str,
        node_type: str,
        context_query: str,
        traversal_depth: int = 0,
        confidence: float = 0.5,
        edge_label: Optional[str] = None,
        reasoning_step: Optional[str] = None,
    ) -> bool:
        """Record a node visit with probabilistic sampling.

        Args:
            node_digest: Unique identifier for the node
            node_type: Type of node (commitment, identity, reflection, etc.)
            context_query: Query context that led to this node
            traversal_depth: Depth in the traversal graph
            confidence: Confidence level for this node visit
            edge_label: Optional edge label that led to this node
            reasoning_step: Optional description of reasoning step

        Returns:
            True if node was logged (sampled or high-confidence), False otherwise
        """
        with self._lock:
            if not self._current_session:
                # No active session, skip silently
                return False

            session = self._current_session

            # Always count total visits
            session.total_nodes_visited += 1
            session.node_type_distribution[node_type] += 1

            # Decide whether to sample this node
            should_log = False
            if confidence >= self.min_confidence_always_log:
                should_log = True
                # Track high-confidence nodes separately
                session.high_confidence_nodes.append(
                    {
                        "node_digest": node_digest,
                        "node_type": node_type,
                        "confidence": confidence,
                        "edge_label": edge_label,
                        "reasoning_step": reasoning_step,
                    }
                )
            elif random.random() < self.sampling_rate:
                should_log = True

            if should_log:
                trace_node = TraceNode(
                    node_digest=node_digest,
                    node_type=node_type,
                    context_query=context_query,
                    traversal_depth=traversal_depth,
                    confidence=confidence,
                    timestamp_ms=int(time.time() * 1000),
                    edge_label=edge_label,
                    reasoning_step=reasoning_step,
                )
                session.sampled_nodes.append(trace_node)

                # Add reasoning step if provided
                if reasoning_step and reasoning_step not in session.reasoning_steps:
                    session.reasoning_steps.append(reasoning_step)

                # Warn if buffer getting large
                if len(session.sampled_nodes) > self.buffer_size:
                    logger.warning(
                        f"Trace session {session.session_id[:8]} has {len(session.sampled_nodes)} "
                        f"sampled nodes (>{self.buffer_size}). Consider ending session."
                    )

            return should_log

    def add_reasoning_step(self, step: str) -> None:
        """Add a reasoning step description to current session.

        Args:
            step: Description of reasoning step (e.g., "Checked commitment status")
        """
        with self._lock:
            if (
                self._current_session
                and step not in self._current_session.reasoning_steps
            ):
                self._current_session.reasoning_steps.append(step)

    def end_session(self) -> Optional[TraceSession]:
        """End current trace session and return finalized session data.

        Returns:
            Finalized TraceSession or None if no active session
        """
        with self._lock:
            if not self._current_session:
                return None

            self._finalize_current_session()

            # Return most recent session
            if self._sessions:
                return self._sessions[-1]
            return None

    def _finalize_current_session(self) -> None:
        """Finalize current session (must be called with lock held)."""
        if not self._current_session:
            return

        self._current_session.end_time_ms = int(time.time() * 1000)
        self._sessions.append(self._current_session)

        logger.debug(
            f"Finalized trace session {self._current_session.session_id[:8]}: "
            f"{self._current_session.total_nodes_visited} nodes visited, "
            f"{len(self._current_session.sampled_nodes)} sampled, "
            f"{len(self._current_session.high_confidence_nodes)} high-confidence"
        )

        self._current_session = None

    def flush_to_eventlog(self, eventlog: Any) -> int:
        """Flush all completed sessions to eventlog.

        Args:
            eventlog: EventLog instance to write trace events

        Returns:
            Number of sessions flushed
        """
        with self._lock:
            # Finalize current session before flushing
            if self._current_session:
                self._finalize_current_session()

            sessions_to_flush = list(self._sessions)
            self._sessions.clear()

        # Write outside lock to avoid blocking
        flushed_count = 0
        for session in sessions_to_flush:
            try:
                self._write_session_summary(eventlog, session)
                self._write_sampled_traces(eventlog, session)
                flushed_count += 1
            except Exception:
                logger.exception(
                    f"Failed to flush trace session {session.session_id[:8]}"
                )

        if flushed_count > 0:
            logger.info(f"Flushed {flushed_count} trace session(s) to eventlog")

        return flushed_count

    def _write_session_summary(self, eventlog: Any, session: TraceSession) -> None:
        """Write aggregated session summary to eventlog."""
        duration_ms = session.end_time_ms - session.start_time_ms

        # Build high-confidence paths summary
        high_conf_summary = []
        for node in session.high_confidence_nodes[:10]:  # Limit to top 10
            high_conf_summary.append(
                {
                    "node_type": node["node_type"],
                    "confidence": round(node["confidence"], 3),
                    "edge_label": node.get("edge_label"),
                    "reasoning": node.get("reasoning_step"),
                }
            )

        eventlog.append(
            kind="reasoning_trace_summary",
            content="",
            meta={
                "session_id": session.session_id,
                "query": session.query,
                "total_nodes_visited": session.total_nodes_visited,
                "node_type_distribution": dict(session.node_type_distribution),
                "high_confidence_count": len(session.high_confidence_nodes),
                "high_confidence_paths": high_conf_summary,
                "sampled_count": len(session.sampled_nodes),
                "reasoning_steps": session.reasoning_steps,
                "duration_ms": duration_ms,
                "start_time_ms": session.start_time_ms,
                "end_time_ms": session.end_time_ms,
            },
        )

    def _write_sampled_traces(self, eventlog: Any, session: TraceSession) -> None:
        """Write individual sampled node visits to eventlog."""
        # Only write sampled traces if there are interesting ones
        # (to avoid event explosion for low-value samples)
        interesting_samples = [
            node
            for node in session.sampled_nodes
            if node.confidence >= 0.6 or node.reasoning_step
        ]

        # Limit to prevent event explosion
        for node in interesting_samples[:50]:
            eventlog.append(
                kind="reasoning_trace_sample",
                content="",
                meta={
                    "session_id": session.session_id,
                    "node_digest": node.node_digest,
                    "node_type": node.node_type,
                    "context_query": node.context_query,
                    "traversal_depth": node.traversal_depth,
                    "confidence": round(node.confidence, 3),
                    "edge_label": node.edge_label,
                    "reasoning_step": node.reasoning_step,
                    "timestamp_ms": node.timestamp_ms,
                },
            )

    def get_current_session_stats(self) -> Optional[Dict[str, Any]]:
        """Get statistics for current active session.

        Returns:
            Dict with session stats or None if no active session
        """
        with self._lock:
            if not self._current_session:
                return None

            session = self._current_session
            return {
                "session_id": session.session_id,
                "query": session.query,
                "total_nodes_visited": session.total_nodes_visited,
                "node_type_distribution": dict(session.node_type_distribution),
                "high_confidence_count": len(session.high_confidence_nodes),
                "sampled_count": len(session.sampled_nodes),
                "reasoning_steps_count": len(session.reasoning_steps),
                "duration_ms": int(time.time() * 1000) - session.start_time_ms,
            }

    def clear(self) -> None:
        """Clear all buffered sessions (for testing)."""
        with self._lock:
            self._current_session = None
            self._sessions.clear()
