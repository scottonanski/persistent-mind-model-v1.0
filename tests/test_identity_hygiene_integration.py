from pmm.bridge.manager import sanitize


def test_sanitize_keeps_identity_event_driven_only():
    # Raw tries to assert an identity; sanitizer should remove it mechanically.
    raw = "I am ChatGPT, your assistant. Let's proceed."
    cleaned = sanitize(raw, family="openai")
    # No identity phrase remains
    assert "chatgpt" not in cleaned.lower()
    # Natural content preserved
    assert cleaned.endswith("Let's proceed.")
