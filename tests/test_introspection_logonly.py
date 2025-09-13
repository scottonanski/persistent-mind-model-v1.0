from pmm.runtime.introspection import run_introspection


def test_run_introspection_logs_single_report_event_only():
    appended = []

    def fake_llm(prompt: str) -> str:
        # Return deterministic text (could also assert on prompt shape here)
        return (
            "Reflections are appended before evidence candidates in the current build."
        )

    def append_event(ev: dict):
        appended.append(ev)

    res = run_introspection(
        topic="reflection-order",
        scope="runtime",
        llm=fake_llm,
        append_event=append_event,
    )

    assert res.summary.startswith("Reflections are appended")
    # Exactly one event appended, with the right kind/payload
    assert len(appended) == 1
    ev = appended[0]
    assert ev["kind"] == "introspection_report"
    assert ev["payload"]["topic"] == "reflection-order"
    assert ev["payload"]["scope"] == "runtime"
    assert "Reflections are appended" in ev["payload"]["summary"]
