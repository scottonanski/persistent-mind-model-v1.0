from pmm.storage.eventlog import EventLog
from pmm.runtime.context_builder import build_context_from_ledger


def _create_sample_ledger() -> EventLog:
    """Return an in-memory EventLog pre-populated with minimal sample data."""
    log = EventLog(":memory:")
    # Identity
    log.append("identity_adopt", "Persistent", meta={"name": "Persistent"})
    # Trait update
    log.append("trait_update", "", meta={"trait": "openness", "delta": 0.14})
    # Open commitment
    log.append(
        "commitment_open",
        "Maintain basic conversational responsiveness",
        meta={"cid": "c1", "text": "Maintain basic conversational responsiveness"},
    )
    # Autonomy tick (IAS/GAS)
    log.append(
        "autonomy_tick",
        "",
        meta={"telemetry": {"IAS": 0.5, "GAS": 0.02}, "stage": "S0"},
    )
    # Reflection
    log.append(
        "reflection",
        "Observation: I need to improve clarity and focus.",
        meta={},
    )
    return log


def test_context_block_contains_core_sections():
    log = _create_sample_ledger()
    block = build_context_from_ledger(log, n_reflections=1)
    # Ensure deterministic markers
    assert block.startswith("[SYSTEM STATE — from ledger]")
    assert "Identity: Persistent" in block
    assert "IAS=0.50, GAS=0.02" in block
    assert "Open commitments:" in block
    assert "Maintain basic conversational responsiveness" in block
    assert "Recent reflections:" in block


def test_context_block_deterministic():
    log = _create_sample_ledger()
    block1 = build_context_from_ledger(log, n_reflections=1)
    block2 = build_context_from_ledger(log, n_reflections=1)
    assert block1 == block2
