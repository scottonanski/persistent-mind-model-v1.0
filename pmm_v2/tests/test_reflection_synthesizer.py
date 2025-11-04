from __future__ import annotations

from pmm_v2.core.event_log import EventLog
from pmm_v2.runtime.reflection_synthesizer import synthesize_reflection


def test_synthesize_reflection_deterministic(tmp_path):
    db = tmp_path / "refl9.db"
    log = EventLog(str(db))
    # seed one turn
    log.append(kind="user_message", content="hello", meta={})
    log.append(kind="assistant_message", content="hi there", meta={})
    log.append(
        kind="metrics_turn",
        content="provider:dummy,model:,in_tokens:2,out_tokens:2,lat_ms:0",
        meta={},
    )

    r1_id = synthesize_reflection(log)
    # remove it and synthesize again to compare content determinism
    events = log.read_all()[:-1]
    # rebuild DB quickly by re-appending (keeps same content deterministically)
    log2 = EventLog(str(tmp_path / "refl9_b.db"))
    for e in events:
        log2.append(kind=e["kind"], content=e["content"], meta=e["meta"])
    r2_id = synthesize_reflection(log2)

    r1 = [e for e in log.read_all() if e["id"] == r1_id][0]
    r2 = [e for e in log2.read_all() if e["id"] == r2_id][0]
    assert r1["content"] == r2["content"]
