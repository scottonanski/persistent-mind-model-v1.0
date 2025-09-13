from pmm.runtime.reflection_guidance import build_reflection_guidance


def test_prompt_composition_uses_guidance_when_present():
    evs = [
        {
            "kind": "autonomy_directive",
            "id": 1,
            "payload": {
                "content": "Use concrete evidence.",
                "meta": {"source": "reply"},
            },
        },
    ]
    g = build_reflection_guidance(evs)
    base = "Reflect on failures in the last 3 turns."
    prompt = (g["text"] + "\n\n" + base) if g["text"] else base
    assert "Guidance:" in prompt
    assert "Use concrete evidence." in prompt
