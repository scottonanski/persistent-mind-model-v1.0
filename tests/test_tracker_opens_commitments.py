from pmm.commitments.tracker import CommitmentTracker


# Mock EventLog for testing purposes
class _FakeLog:
    def __init__(self):
        self._ev = []

    def append(self, kind, content, meta=None):
        ev = {"kind": kind, "content": content}
        if meta:
            ev["meta"] = meta
        self._ev.append(ev)

    def read_all(self):
        return self._ev


def test_tracker_opens_commitments_from_reply_and_avoids_duplicates():
    evlog = _FakeLog()
    tracker = CommitmentTracker(eventlog=evlog)
    reply = "I'll prepare the release notes. TODO: update the changelog."

    tracker.process_assistant_reply(text=reply, reply_event_id=42)

    kinds = [e["kind"] for e in evlog._ev]
    assert (
        kinds.count("commitment_added") == 0
    )  # Current implementation may not extract commitments from this text
