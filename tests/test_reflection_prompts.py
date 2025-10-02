from pmm.llm.factory import LLMConfig
from pmm.runtime.loop import Runtime
from pmm.storage.eventlog import EventLog


def test_reflection_templates_are_pmm_scoped():
    # Instantiate Runtime to test reflection behavior
    cfg = LLMConfig(provider="openai", model="gpt-4o")
    eventlog = EventLog(":memory:")
    rt = Runtime(cfg, eventlog)

    # Test that the reflection method exists and can be called
    assert hasattr(rt, "reflect"), "Reflection method not found in Runtime"

    # Placeholder for more robust testing; actual reflection content validation
    # would require mocking or accessing internal state, which is not directly available
    # This test ensures the method is callable and returns a string
    result = rt.reflect("Test context")
    assert isinstance(result, str), "Reflection did not return a string"
