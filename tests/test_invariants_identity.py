from __future__ import annotations

from pmm.runtime import invariants_rt


def test_identity_adopt_allows_user_source_without_propose():
    events = [
        {"kind": "identity_adopt", "content": "Echo", "meta": {"source": "user"}},
    ]
    violations = invariants_rt.check_identity_propose_before_adopt(events)
    assert not violations  # user-sourced adopt is allowed without propose
