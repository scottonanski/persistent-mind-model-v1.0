from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import Runtime
from pmm.llm.factory import LLMConfig
from pmm.llm.limits import MAX_CHAT_CALLS_PER_TICK


def _new_runtime(tmp_path):
    db = tmp_path / "quota_latency.db"
    log = EventLog(str(db))
    cfg = LLMConfig(provider="openai", model="gpt-3.5-turbo")
    rt = Runtime(cfg, log)
    return rt


def test_llm_latency_emitted_for_reflection_chat(tmp_path):
    rt = _new_runtime(tmp_path)
    rt.reflect("Context for latency test.")
    evs = rt.eventlog.read_all()
    lat = [
        e
        for e in evs
        if e.get("kind") == "llm_latency" and (e.get("meta") or {}).get("op") == "chat"
    ]
    assert lat, "Expected at least one llm_latency event for chat"
    m = lat[-1].get("meta") or {}
    # Shape checks
    assert "provider" in m and "model" in m and "ms" in m and "ok" in m
    assert isinstance(m.get("ms"), float)
    assert isinstance(m.get("ok"), bool)


def test_rate_limit_skip_emitted_when_exceeding_budget(tmp_path):
    rt = _new_runtime(tmp_path)
    n_calls = MAX_CHAT_CALLS_PER_TICK + 2
    for i in range(n_calls):
        rt.reflect(f"Budget test {i}")
    evs = rt.eventlog.read_all()
    # We should still have a reflection per call (non-blocking behavior)
    reflections = [e for e in evs if e.get("kind") == "reflection"]
    assert len(reflections) >= n_calls
    # And at least one rate_limit_skip for chat after exceeding budget
    skips = [
        e
        for e in evs
        if e.get("kind") == "rate_limit_skip"
        and (e.get("meta") or {}).get("op") == "chat"
    ]
    assert (
        skips
    ), "Expected rate_limit_skip event(s) when exceeding per-tick chat budget"
