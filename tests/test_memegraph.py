from __future__ import annotations

from pathlib import Path

from pmm.runtime.memegraph import MemeGraphProjection
from pmm.storage.eventlog import EventLog


def _make_eventlog(tmp_path: Path) -> EventLog:
    db_path = tmp_path / "ledger.db"
    return EventLog(str(db_path))


def test_memegraph_initial_build(tmp_path):
    log = _make_eventlog(tmp_path)
    log.append(
        "identity_adopt",
        "Alpha",
        {"name": "Alpha", "sanitized": "Alpha", "confidence": 0.95},
    )
    log.append(
        "commitment_open",
        "",
        {"cid": "C1", "text": "Document the mirror layer."},
    )
    graph = MemeGraphProjection(log)
    assert graph.node_count >= 3
    assert graph.edge_count >= 2
    metrics = graph.last_batch_metrics
    assert metrics["nodes"] == graph.node_count
    assert metrics["edges"] == graph.edge_count


def test_memegraph_updates_on_append(tmp_path):
    log = _make_eventlog(tmp_path)
    graph = MemeGraphProjection(log)
    initial_nodes = graph.node_count
    log.append(
        "reflection",
        "",
        {"prompt_template": "succinct", "tag": "analysis"},
    )
    log.append(
        "policy_update",
        "",
        {"component": "reflection", "src_id": 1},
    )
    assert graph.node_count > initial_nodes
    metrics = graph.last_batch_metrics
    assert metrics["batch_events"] >= 1
    before_rebuild_nodes = graph.node_count
    graph.rebuild()
    assert graph.node_count == before_rebuild_nodes
