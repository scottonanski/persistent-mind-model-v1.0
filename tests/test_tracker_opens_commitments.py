from pmm.commitments.tracker import CommitmentTracker


class _FakeLog:
    def __init__(self):
        self._ev = []

    def read_all(self):
        return list(self._ev)

    def append(self, *, kind: str, content: str, meta: dict):
        self._ev.append({"kind": kind, "content": content, "meta": meta})
        return len(self._ev)


def test_tracker_opens_commitments_from_reply_and_avoids_duplicates():
    evlog = _FakeLog()
    tracker = CommitmentTracker(eventlog=evlog)
    reply = "I'll prepare the release notes. TODO: update the changelog."

    tracker.process_assistant_reply(text=reply, reply_event_id=42)

    kinds = [e["kind"] for e in evlog._ev]
    assert kinds.count("commitment_open") == 2

    # idempotency on second call with same reply
    tracker.process_assistant_reply(text=reply, reply_event_id=43)
    kinds2 = [e["kind"] for e in evlog._ev]
    assert kinds2.count("commitment_open") == 2  # still two, no dup

    contents = [e.get("content") for e in evlog._ev if e["kind"] == "commitment_open"]
    assert any("prepare the release notes" in (c or "").lower() for c in contents)
    assert any("update the changelog" in (c or "").lower() for c in contents)

    # origin_eid is linked for auditability
    metas = [e.get("meta") for e in evlog._ev if e["kind"] == "commitment_open"]
    assert all("origin_eid" in m for m in metas)
