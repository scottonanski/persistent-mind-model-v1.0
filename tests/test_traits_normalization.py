from __future__ import annotations

from pmm.runtime.self_evolution import SelfEvolution
from pmm.runtime.traits import normalize_key


def test_legacy_caps_trait_is_read_and_lowercase_emitted():
    legacy_key = "traits.Conscientiousness"
    events = [
        {
            "kind": "evolution",
            "meta": {"tick": 1, "changes": {legacy_key: 0.52}},
            "content": {},
        },
    ]
    changes, _ = SelfEvolution.apply_policies(events, {"IAS": 0.5, "GAS": 0.5})
    assert not any(
        k.startswith("traits.") and any(c.isupper() for c in k) for k in changes.keys()
    )
    for key in changes.keys():
        assert key == key.lower()

    canonical = f"traits.{normalize_key('conscientiousness')}"
    cur = SelfEvolution._last_setting_from_evolution(
        events, canonical, SelfEvolution.DEFAULT_CONSCIENTIOUSNESS
    )
    assert round(float(cur), 2) == 0.52
