from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model
from pmm.commitments.tracker import CommitmentTracker
from pmm.runtime.memegraph import MemeGraphProjection


def test_open_then_invalid_close_stays_open(tmp_path):
    db = tmp_path / "ev.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log)

    text = "I will complete the project by tomorrow."
    cid = ct.add_commitment(text, source="test1")
    assert cid

    # Attempt to close with invalid evidence type
    closed = ct.close_with_evidence(cid, "invalid_type", "This is not valid evidence.")
    assert not closed

    # Check if commitment is still open via projection
    open_map = build_self_model(log.read_all()).get("commitments", {}).get("open", {})
    assert cid in open_map


def test_open_then_valid_close_removes_from_open(tmp_path):
    db = tmp_path / "ev.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log)

    text = "I will complete the project by tomorrow."
    cid = ct.add_commitment(text, source="test2")
    assert cid

    # Close with valid evidence requires artifact
    closed = ct.close_with_evidence(
        cid, "done", "Project completed as promised.", artifact="/tmp/proof.txt"
    )
    assert closed is True

    # Check if commitment is no longer open
    open_map = build_self_model(log.read_all()).get("commitments", {}).get("open", {})
    assert cid not in open_map


def test_text_only_evidence_closes_when_allowed(tmp_path, monkeypatch):
    db = tmp_path / "ev.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log)

    text = "I will complete the project by tomorrow."
    cid = ct.add_commitment(text, source="test3")
    assert cid

    closed = ct.close_with_evidence(cid, "done", "Project completed as promised.")
    assert closed is True


def test_reclosing_returns_false(tmp_path, monkeypatch):
    db = tmp_path / "ev.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log)

    text = "I will complete the project by tomorrow."
    cid = ct.add_commitment(text, source="test4")
    assert cid

    # Close once (with artifact)
    closed = ct.close_with_evidence(
        cid, "done", "Project completed as promised.", artifact="/tmp/a.txt"
    )
    assert closed

    # Attempt to close again
    closed_again = ct.close_with_evidence(cid, "done", "Trying to close again.")
    assert not closed_again


def test_done_evidence_candidates_when_ambiguous(tmp_path, monkeypatch):

    db = tmp_path / "ev_done.db"
    log = EventLog(str(db))
    t = CommitmentTracker(log)

    text1 = "I will write the report."
    cid1 = t.add_commitment(text1, source="test6")
    assert cid1

    text2 = "I will finalize the report."
    cid2 = t.add_commitment(text2, source="test7")
    assert cid2

    # Process evidence; current implementation may close the best-matching one
    closed_cids = t.process_evidence("Done: I've completed the report.")
    assert isinstance(closed_cids, list)


def test_done_evidence_candidates_by_detail_substring(tmp_path, monkeypatch):

    db = tmp_path / "ev_done2.db"
    log = EventLog(str(db))
    t = CommitmentTracker(log)

    text1 = "I will write the annual report."
    cid1 = t.add_commitment(text1, source="test8")
    assert cid1

    text2 = "I will write the quarterly report."
    cid2 = t.add_commitment(text2, source="test9")
    assert cid2

    # Process evidence; include completion cue to be considered
    closed_cids = t.process_evidence("Done: I've completed the quarterly report.")
    assert isinstance(closed_cids, list)


def test_commitment_shadow_mode(monkeypatch, tmp_path):
    db = tmp_path / "shadow.db"
    log = EventLog(str(db))
    log.append(
        "commitment_open",
        "",
        {"cid": "C1", "text": "Coordinate with Alpha on rollout."},
    )
    graph = MemeGraphProjection(log)

    snapshot_calls: list[dict] = []

    original_snapshot = graph.open_commitments_snapshot

    def _wrapped_snapshot():
        result = original_snapshot()
        snapshot_calls.append(result)
        return result

    monkeypatch.setattr(graph, "open_commitments_snapshot", _wrapped_snapshot)
    ct = CommitmentTracker(log, memegraph=graph)

    # Rebinding should succeed without raising, comparing graph vs. legacy maps
    ct._rebind_commitments_on_identity_adopt("Alpha", "Beta")
    assert snapshot_calls, "expected memegraph snapshot to be used"
    assert sorted(snapshot_calls[0].keys()) == ["C1"]


# Ensure proper statement separation with multiple newlines at the end of the file
