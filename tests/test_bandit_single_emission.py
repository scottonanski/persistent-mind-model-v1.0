from pmm.runtime.loop import AutonomyLoop
from pmm.storage.eventlog import EventLog


class _CDAlwaysOK:
    def should_reflect(self, *args, **kwargs):
        return (True, "ok")

    def reset(self):
        pass


def test_single_bandit_emission_and_order(tmp_path):
    db = tmp_path / "bandit.db"
    log = EventLog(str(db))

    loop = AutonomyLoop(eventlog=log, cooldown=_CDAlwaysOK(), interval_seconds=0.01)
    loop.tick()

    evs = log.read_all()
    bandits = [e for e in evs if e.get("kind") == "bandit_arm_chosen"]
    assert len(bandits) == 1

    # Ensure bandit appears after insight_ready for the reflection in this tick
    last_insight_id = 0
    bandit_id = 10**9
    for e in evs:
        if e.get("kind") == "insight_ready":
            try:
                last_insight_id = int(e.get("id") or 0)
            except Exception:
                last_insight_id = 0
        if e.get("kind") == "bandit_arm_chosen":
            try:
                bandit_id = int(e.get("id") or 0)
            except Exception:
                bandit_id = 0
            break
    assert bandit_id > last_insight_id
