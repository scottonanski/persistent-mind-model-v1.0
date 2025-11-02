from __future__ import annotations

import pytest

from pmm.runtime.context_builder import build_context_from_ledger
from pmm.runtime.loop.identity import sanitize_name
from pmm.storage.eventlog import EventLog


def _tmp_eventlog(tmp_path) -> EventLog:
    db = tmp_path / "test.db"
    return EventLog(str(db))


def test_context_is_deterministic(tmp_path):
    log = _tmp_eventlog(tmp_path)

    # Append a small, bounded set of events
    log.append(kind="user", content="hello", meta={})
    log.append(kind="identity_adopt", content="Echo", meta={"name": "Echo"})
    log.append(kind="response", content="I will do X", meta={})

    ctx1 = build_context_from_ledger(log, use_tail_optimization=True)
    ctx2 = build_context_from_ledger(log, use_tail_optimization=True)

    assert isinstance(ctx1, str) and isinstance(ctx2, str)
    assert ctx1 == ctx2


@pytest.mark.parametrize(
    "name,expected",
    [
        ("What", None),
        ("Or", None),
        ("Not", None),
        ("how", None),
        ("why", None),
        ("when", None),
        ("9lives", None),
        ("Al", None),  # too short (<3)
        ("Echo", "Echo"),
        ("echo_1", "echo_1"),
    ],
)
def test_sanitize_name_edge_cases(name, expected):
    assert sanitize_name(name) == expected
