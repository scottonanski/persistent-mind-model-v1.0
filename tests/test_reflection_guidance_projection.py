from pmm.runtime.reflection_guidance import build_reflection_guidance


def test_guidance_formats_active_set_deterministically():
    evs = [
        {
            "kind": "autonomy_directive",
            "id": 10,
            "payload": {
                "content": "Keep replies concise.",
                "meta": {"source": "reply"},
            },
        },
        {
            "kind": "autonomy_directive",
            "id": 11,
            "payload": {
                "content": "Prefer evidence-linked closures.",
                "meta": {"source": "reflection"},
            },
        },
        {
            "kind": "autonomy_directive",
            "id": 200,
            "payload": {
                "content": "Keep replies concise.",
                "meta": {"source": "reply"},
            },
        },
    ]
    g = build_reflection_guidance(evs, top_k=2)
    assert g["items"][0]["content"].lower().startswith("keep replies")
    assert g["text"].startswith("Guidance:\n- ")
