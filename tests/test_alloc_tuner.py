from pmm.runtime.alloc_tuner import AllocTuner


def test_alloc_tuner_scales_with_length_stops(tmp_path, monkeypatch):
    p = tmp_path / "tuner.json"
    t = AllocTuner(path=str(p), window=100)
    # Feed 60% length stops → should scale up gradually (<= 1.30)
    for i in range(60):
        t.record(
            model_key="m",
            task="reflect_recursive",
            prompt_tokens=1000,
            target_out=800,
            completion_tokens=790,
            stop_reason="length",
        )
    for i in range(40):
        t.record(
            model_key="m",
            task="reflect_recursive",
            prompt_tokens=1000,
            target_out=800,
            completion_tokens=500,
            stop_reason="stop",
        )
    s = t.get_scale(model_key="m", task="reflect_recursive")
    assert 1.0 <= s <= 1.30


def test_alloc_tuner_scales_down_on_underuse(tmp_path):
    p = tmp_path / "tuner.json"
    t = AllocTuner(path=str(p), window=100)
    # Underuse: very low completion vs target and almost no length stops
    for i in range(97):
        t.record(
            model_key="m2",
            task="chat",
            prompt_tokens=500,
            target_out=1000,
            completion_tokens=300,
            stop_reason="stop",
        )
    for i in range(3):
        t.record(
            model_key="m2",
            task="chat",
            prompt_tokens=500,
            target_out=1000,
            completion_tokens=700,
            stop_reason="length",
        )
    s = t.get_scale(model_key="m2", task="chat")
    assert 0.80 <= s <= 1.0
