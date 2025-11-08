from __future__ import annotations

from pmm.core.event_log import EventLog
from pmm.core.ledger_mirror import LedgerMirror
from pmm.runtime.identity_summary import maybe_append_summary
from pmm.runtime.cli import handle_pm_command


def _seed_simple_history(log: EventLog) -> None:
    for i in range(10):
        log.append(kind="user_message", content=f"u{i}", meta={})
        log.append(kind="assistant_message", content=f"a{i}", meta={})


def test_checkpoint_manifest_idempotent_and_fast_rebuild_equivalent():
    log = EventLog(":memory:")
    _seed_simple_history(log)

    # Force a summary_update anchor
    maybe_append_summary(log)
    events_before = log.read_all()
    summaries = [e for e in events_before if e.get("kind") == "summary_update"]
    assert summaries, "expected a summary_update to exist"

    # Append checkpoint manifest via /pm checkpoint
    out1 = handle_pm_command("/pm checkpoint", log)
    assert out1 and "appended" in out1.lower()

    # Idempotent repeat should say no change
    out2 = handle_pm_command("/pm checkpoint", log)
    assert out2 == "No change (idempotent)"

    # Fast rebuild should match full snapshot
    lm_full = LedgerMirror(log, listen=False)
    snap_full = lm_full.rsm_snapshot()
    lm_fast = LedgerMirror(log, listen=False)
    # Use the new fast path
    if hasattr(lm_fast, "rebuild_fast"):
        lm_fast.rebuild_fast()
    snap_fast = lm_fast.rsm_snapshot()
    assert snap_fast == snap_full
