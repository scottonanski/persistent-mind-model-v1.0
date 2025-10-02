from pmm.commitments.tracker import CommitmentTracker
from pmm.runtime.recall import suggest_recall
from pmm.storage.eventlog import EventLog


def test_suggests_relevant_prior_events(tmp_path):
    db = tmp_path / "recall1.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log)

    # Open a commitment event
    cid = ct.add_commitment("write the report", source="test")
    assert cid

    # Simulate a later assistant reply mentioning the same topic
    reply = "Working on the report now"
    log.append(kind="response", content=reply, meta={})

    evs = log.read_all()
    sugg = suggest_recall(evs, reply)
    assert isinstance(sugg, list)
    assert len(sugg) >= 1
    # The first suggestion should point to the earlier commitment event
    # Ensure we append a recall_suggest like the runtime would
    latest_id = evs[-1]["id"]
    clean = [
        {"eid": s["eid"], "snippet": s["snippet"]} for s in sugg if s["eid"] < latest_id
    ][:3]
    assert clean


def test_deterministic_ordering(tmp_path):
    db = tmp_path / "recall2.db"
    log = EventLog(str(db))
    # Create two prior events with equal overlap
    log.append(kind="response", content="alpha beta", meta={})
    log.append(kind="response", content="alpha beta", meta={})
    reply = "alpha beta"
    log.append(kind="response", content=reply, meta={})

    evs = log.read_all()
    sugg = suggest_recall(evs, reply)
    # With equal scores, tie-break by earlier eid -> e1 before e2
    ids = [s["eid"] for s in sugg]
    assert ids == sorted(ids)


def test_empty_when_no_relevance(tmp_path):
    db = tmp_path / "recall3.db"
    log = EventLog(str(db))
    # Prior event unrelated
    log.append(kind="response", content="hello world", meta={})
    reply = "unrelated topic"
    log.append(kind="response", content=reply, meta={})

    evs = log.read_all()
    sugg = suggest_recall(evs, reply)
    assert sugg == []
