from pmm.runtime.introspection import build_prompt


def test_build_prompt_is_deterministic_and_contains_fields():
    p = build_prompt(topic="reflection-order", scope="runtime")
    assert p.startswith("[INTROSPECTION]")
    assert "Topic: reflection-order" in p
    assert "Scope: runtime" in p
    assert "Do not propose actions." in p
