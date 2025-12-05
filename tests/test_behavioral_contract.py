import json
import hashlib

import pytest

from pmm.core.event_log import EventLog
from pmm.runtime.loop import RuntimeLoop


class MockAdapter:
    """Mock adapter matching RuntimeLoop interface: generate_reply -> str."""

    def __init__(self, response_text: str) -> None:
        self.response_text = response_text

    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        return self.response_text


@pytest.fixture
def temp_eventlog(tmp_path):
    return EventLog(path=":memory:")


def test_markers_to_ledger_events(temp_eventlog: EventLog) -> None:
    title = "test_commitment"
    cid = hashlib.sha1(title.encode("utf-8")).hexdigest()[:8]
    mock_response = f"""
Test response.

COMMIT: {title}
CLAIM:identity_proposal={{\"token\": \"test_self\", \"description\": \"Test identity\", \"evidence_events\": []}}
REFLECT: {{\"observations\": [\"obs1\"], \"next\": [\"continue\"], \"corrections\": []}}
CLOSE: {cid}

End.
"""
    adapter = MockAdapter(mock_response)
    loop = RuntimeLoop(
        eventlog=temp_eventlog,
        adapter=adapter,
        autonomy=False,
        replay=False,
    )

    loop.run_turn("Test user prompt")

    events = temp_eventlog.read_all()

    # commitment_open: content "Commitment opened: <text>", meta["text"] == "test_commitment"
    opens = [e for e in events if e["kind"] == "commitment_open"]
    assert any(e.get("meta", {}).get("text") == "test_commitment" for e in opens)

    # claim: content "CLAIM:identity_proposal=...", meta.claim_type == "identity_proposal"
    claims = [e for e in events if e["kind"] == "claim"]
    assert any(
        e.get("content", "").startswith("CLAIM:identity_proposal=")
        and (e.get("meta") or {}).get("claim_type") == "identity_proposal"
        for e in claims
    )

    # reflection: at least one exists; we do not assert exact shape
    reflections = [e for e in events if e["kind"] == "reflection"]
    assert len(reflections) >= 1

    # commitment_close: content "Commitment closed: <cid>"; cid must match the open cid
    closes = [e for e in events if e["kind"] == "commitment_close"]
    assert len(closes) >= 1
    open_cids = {e.get("meta", {}).get("cid") for e in opens}
    assert any((e.get("meta") or {}).get("cid") in open_cids for e in closes)


def test_identity_adoption_flow(temp_eventlog: EventLog) -> None:
    propose_response = """
Propose.

CLAIM:identity_proposal={"token": "test_self", "description": "Test", "evidence_events": []}
"""
    ratify_response = """
Ratify.

CLAIM:identity_ratify={"token": "test_self"}
"""

    adapter = MockAdapter(propose_response)
    loop = RuntimeLoop(
        eventlog=temp_eventlog,
        adapter=adapter,
        autonomy=False,
        replay=False,
    )

    loop.run_turn("Propose identity")

    adapter.response_text = ratify_response
    loop.run_turn("Ratify identity")

    events = temp_eventlog.read_all()
    adoptions = [e for e in events if e["kind"] == "identity_adoption"]
    assert len(adoptions) >= 1
    assert any(json.loads(e["content"]).get("token") == "test_self" for e in adoptions)


def test_no_marker_driven_events_on_indented_markers(temp_eventlog: EventLog) -> None:
    indented_response = """
Indented.

  COMMIT: bad
**CLAIM:**identity_proposal={"token": "bad"}
"""
    adapter = MockAdapter(indented_response)
    loop = RuntimeLoop(
        eventlog=temp_eventlog,
        adapter=adapter,
        autonomy=False,
        replay=False,
    )

    loop.run_turn("Test indented")

    events = temp_eventlog.read_all()
    # Reflections are allowed; we only forbid marker-driven kinds
    assert not any(
        e["kind"]
        in ("commitment_open", "commitment_close", "claim", "identity_adoption")
        for e in events
    )
