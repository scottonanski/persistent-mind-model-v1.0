"""Regression test for graph_slice commitment relations."""

from pathlib import Path

from pmm.runtime.memegraph import MemeGraphProjection
from pmm.storage.eventlog import EventLog


def _make_eventlog(tmp_path: Path) -> EventLog:
    db_path = tmp_path / "ledger.db"
    return EventLog(str(db_path))


def test_graph_slice_returns_commitment_relations(tmp_path):
    """Regression test: graph_slice should return commitment relations after confidence fix."""
    log = _make_eventlog(tmp_path)

    # Seed ledger with commitment events
    log.append(
        "commitment_open",
        "",
        {"cid": "C1", "text": "Test commitment for graph slice"},
    )
    log.append(
        "commitment_open",
        "",
        {"cid": "C2", "text": "Another commitment about project planning"},
    )

    # Add some related events for richer graph
    log.append(
        "reflection",
        "Thinking about commitments and planning",
        {"source": "reflect", "telemetry": {"IAS": 0.7, "GAS": 0.8}},
    )

    graph = MemeGraphProjection(log)

    # Query for commitment-related topics
    relations = graph.graph_slice("commitment", limit=5, min_confidence=0.6)

    # Should find commitment relations (not filtered out by low confidence)
    assert len(relations) > 0, "graph_slice should return commitment relations"

    # Verify we get commitment-to-event relations
    commitment_relations = [r for r in relations if r["dst"] == "commitment"]
    assert len(commitment_relations) > 0, "Should find commitment nodes in results"

    # Verify confidence is above threshold
    for relation in relations:
        assert (
            relation["score"] >= 0.6
        ), f"Relation score {relation['score']} should be >= 0.6"

    # Should find relations with real event IDs
    relations_with_ids = [
        r for r in relations if r["src_event_id"] or r["dst_event_id"]
    ]
    assert len(relations_with_ids) > 0, "Should find relations with event IDs"
