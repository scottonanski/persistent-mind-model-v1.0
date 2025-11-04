from __future__ import annotations

import json
import pytest

from pmm_v2.core.semantic_extractor import extract_commitments, extract_claims


def test_extract_commitments_and_claims_valid():
    lines = [
        "Hello",
        "COMMIT: do X",
        "CLAIM:event_existence=" + json.dumps({"id": 1}),
        "COMMIT: do Y",
    ]
    commits = extract_commitments(lines)
    assert commits == ["do X", "do Y"]

    claims = extract_claims(lines)
    assert claims == [("event_existence", {"id": 1})]


def test_extract_claims_invalid_json_raises():
    lines = ["CLAIM:event_existence={not json}"]
    with pytest.raises(ValueError):
        _ = extract_claims(lines)


def test_empty_input_returns_empty_lists():
    assert extract_commitments([]) == []
    assert extract_claims([]) == []

