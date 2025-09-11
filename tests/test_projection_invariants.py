import pytest
from pmm.storage.projection import build_self_model, ProjectionInvariantError


def _ev(kind, **meta):
    return {"kind": kind, "content": "", "meta": meta, "ts": "0"}


def test_commitment_close_requires_evidence():
    events = [
        _ev("commitment_open", cid="c1", text="Do the thing"),
        _ev("commitment_close", cid="c1"),  # invalid without evidence
    ]
    with pytest.raises(ProjectionInvariantError):
        build_self_model(events, strict=True)


def test_commitment_close_with_evidence_passes():
    events = [
        _ev("commitment_open", cid="c1", text="Do the thing"),
        _ev("evidence_candidate", cid="c1", evidence_type="done"),
        _ev("commitment_close", cid="c1"),
    ]
    state = build_self_model(events, strict=True)
    assert "c1" not in state["commitments"]["open"]


def test_trait_update_bounded_and_clamped():
    # Start at 0.5; push a large jump to test bounding + clamp
    events = [
        _ev(
            "trait_update", trait="C", delta=1.5
        ),  # should bound delta to <= max, then clamp
    ]
    state = build_self_model(events, strict=True, max_trait_delta=0.1)
    val = state["identity"]["traits"]["conscientiousness"]
    assert 0.0 <= val <= 1.0
    # with prev=0.5 and max_delta=0.1, expect 0.6 (bounded), not 2.0
    assert abs(val - 0.6) < 1e-6


def test_identity_cannot_silently_revert_to_none():
    events = [
        _ev("identity_adopt", name="Logos"),
        # No identity_clear event
        _ev("trait_update", trait="O", delta=0.2),
        # (nothing else)
    ]
    # No error: still adopted, no revert
    state = build_self_model(events, strict=True)
    assert state["identity"]["name"] == "Logos"

    # Now simulate explicit clear (allowed in strict mode)
    cleared = [
        _ev("identity_adopt", name="Logos"),
        _ev("identity_clear"),
    ]
    state2 = build_self_model(cleared, strict=True)
    assert state2["identity"]["name"] is None
