import time

import pytest
from dotenv import load_dotenv

from pmm.llm.factory import LLMConfig
from pmm.runtime.loop import Runtime
from pmm.storage.eventlog import EventLog

load_dotenv()


@pytest.fixture
def runtime(tmp_path):
    db = tmp_path / "reflect_test.db"
    eventlog = EventLog(str(db))
    cfg = LLMConfig(provider="openai", model="gpt-3.5-turbo")
    rt = Runtime(cfg, eventlog)
    return rt


def test_expressive_reflection_integration(runtime):
    # Simulate several reflections with different contexts
    for i in range(5):
        context = f"Session context {i}."
        runtime.reflect(context)
        time.sleep(0.05)
    events = runtime.eventlog.read_all()
    reflections = [e for e in events if e.get("kind") == "reflection"]
    assert len(reflections) >= 3
    # Check for style and novelty info
    for refl in reflections:
        meta = refl.get("meta") or {}
        assert "style" in meta
        assert "novelty" in meta
    # Check at least one actionable insight and quality event
    actions = [e for e in events if e.get("kind") == "reflection_action"]
    qualities = [e for e in events if e.get("kind") == "reflection_quality"]
    assert len(actions) >= 1
    assert len(qualities) >= len(reflections)
    # Print for manual inspection
    for refl in reflections:
        print(
            f"[TEST] Reflection: {refl['content']} (style={refl['meta'].get('style')}, novelty={refl['meta'].get('novelty')})"
        )
    for act in actions:
        print(f"[TEST] Actionable: {act['content']}")
    for qual in qualities:
        print(f"[TEST] Quality: {qual['meta']}")
