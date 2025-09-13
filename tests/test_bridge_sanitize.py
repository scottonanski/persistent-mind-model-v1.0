from pmm.bridge.manager import sanitize


def test_strips_ai_preamble_and_role_lines():
    raw = "As an AI language model, I can't do XYZ.\nassistant: Hello!\nHere is the answer."
    out = sanitize(raw, family="openai")
    # Preamble and 'assistant:' line removed; content collapsed
    assert "as an ai language model" not in out.lower()
    assert "assistant:" not in out.lower()
    assert out == "I can't do XYZ. Here is the answer."


def test_removes_identity_claims_and_collapses_ws():
    raw = "My name is ChatGPT.   I am a large language model.  Response follows."
    out = sanitize(raw, family="claude")
    assert "my name is" not in out.lower()
    assert "large language model" not in out.lower()
    assert out == "Response follows."
