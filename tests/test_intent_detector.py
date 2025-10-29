from __future__ import annotations

from pmm.commitments.intent_detector import (
    detect_commitment_intent,
    extract_commitment_claims,
)


def test_adjectival_not_commitment():
    s = "My ideal self is a reliable assistant committed to providing accurate information."
    intent, conf = detect_commitment_intent(s)
    assert intent in ("adjectival", "none"), (intent, conf)


def test_first_person_is_commitment():
    s = "I committed to finishing the documentation by Friday."
    intent, conf = detect_commitment_intent(s)
    assert intent == "open"
    assert conf >= 0.60  # deterministic local embeddings; allow modest margin


def test_extract_only_open_commitments_mixed():
    text = (
        "My ideal self is an assistant committed to helping users.\n"
        "I committed to implementing this feature by next week.\n"
        "The system is committed to accuracy.\n"
    )
    claims = extract_commitment_claims(text)
    assert len(claims) == 1
    sentence, intent, conf = claims[0]
    assert intent == "open"
    assert "implementing this feature" in sentence.lower()
