import hashlib
from pmm.storage.eventlog import EventLog
from pmm.constants import EventKinds


def _digest_str(s: str) -> str:
    """Return deterministic digest of a string."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def _seed_reflections(eventlog: EventLog, count: int) -> None:
    """Emit N reflection events with deterministic content."""
    for i in range(count):
        digest = _digest_str(f"reflection-{i}")
        eventlog.append(
            kind=EventKinds.REFLECTION,
            content="",
            meta={"digest": digest, "quality": "ok", "reason": "test"},
        )


def _seed_restructures(eventlog: EventLog, count: int) -> None:
    """Emit N commitment_restructure events with deterministic digests."""
    for i in range(count):
        digest = _digest_str(f"restructure-{i}")
        eventlog.append(
            kind=EventKinds.EVOLUTION,
            content="",
            meta={"digest": digest, "changes": {"commitments": {"merged": i}}},
        )


def _seed_metrics(eventlog: EventLog, ias: float, gas: float) -> None:
    """Emit a deterministic metrics update event for IAS/GAS."""
    digest = _digest_str(f"metrics-{ias}-{gas}")
    eventlog.append(
        kind=EventKinds.METRICS_UPDATE,
        content="",
        meta={
            "digest": digest,
            "IAS": round(ias, 2),
            "GAS": round(gas, 2),
        },
    )


def seed_stage_progression(db_path, upto: str = "S2") -> None:
    """Populate a DB with enough events to reach a given stage."""
    log = EventLog(str(db_path))

    if upto in ("S1", "S2", "S3", "S4"):
        _seed_reflections(log, 3)
        _seed_restructures(log, 2)
        _seed_metrics(log, 0.62, 0.22)  # triggers S0→S1
    if upto in ("S2", "S3", "S4"):
        _seed_reflections(log, 5)
        _seed_restructures(log, 4)
        _seed_metrics(log, 0.72, 0.36)  # triggers S1→S2
    if upto in ("S3", "S4"):
        _seed_reflections(log, 8)
        _seed_restructures(log, 6)
        _seed_metrics(log, 0.81, 0.55)  # triggers S2→S3
    if upto == "S4":
        _seed_reflections(log, 12)
        _seed_restructures(log, 8)
        _seed_metrics(log, 0.88, 0.77)  # triggers S3→S4
