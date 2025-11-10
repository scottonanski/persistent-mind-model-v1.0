# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

import json
from pmm.runtime.reflection_synthesizer import synthesize_kernel_reflection


def test_no_delta_skips_with_last_ref_hash():
    # Build a small slice with increasing ids
    slice_events = [
        {"kind": "autonomy_tick", "id": 1, "content": "{}", "meta": {}},
        {"kind": "autonomy_tick", "id": 2, "content": "{}", "meta": {}},
        {"kind": "autonomy_tick", "id": 3, "content": "{}", "meta": {}},
    ]
    first = synthesize_kernel_reflection(slice_events)
    assert first is not None
    payload, h1 = first
    assert isinstance(payload, dict) and isinstance(h1, str)

    # Append a fake last reflection carrying the same delta_hash
    fake_ref = {
        "kind": "reflection",
        "id": 4,
        "content": json.dumps(payload, sort_keys=True, separators=(",", ":")),
        "meta": {"source": "autonomy_kernel", "delta_hash": h1},
    }
    slice2 = slice_events[-2:] + [fake_ref]
    second = synthesize_kernel_reflection(slice2)
    assert second is None


def test_deterministic_output_stable():
    slice1 = [
        {"kind": "user_message", "id": 10, "content": "hi", "meta": {}},
        {"kind": "assistant_message", "id": 11, "content": "determinism", "meta": {}},
    ]
    a = synthesize_kernel_reflection(slice1)
    b = synthesize_kernel_reflection(slice1)
    assert a is not None and b is not None
    (pa, _ha) = a
    (pb, _hb) = b
    assert json.dumps(pa, sort_keys=True, separators=(",", ":")) == json.dumps(
        pb, sort_keys=True, separators=(",", ":")
    )
