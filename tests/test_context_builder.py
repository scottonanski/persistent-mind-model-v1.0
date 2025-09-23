from pmm.storage.eventlog import EventLog
import re
from pmm.runtime.context_builder import build_context_from_ledger, build_context


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


def test_context_builder_includes_trait_suggestion_guidance():
    """Test that context builder includes trait suggestion guidance."""
    # Build a minimal context (mock traits + metrics)
    context = build_context(
        traits={"O": 0.7, "C": 0.5, "E": 0.4, "A": 0.6, "N": 0.3},
        metrics={"IAS": 0.1, "GAS": 0.2},
        stage="S0",
    )

    # Join context lines into a single string for searching
    context_text = "\n".join(context)

    # Assert that trait-adjustment guidance appears
    assert re.search(
        r"personality adjustments.*I should increase openness by 0\.02",
        context_text,
        re.IGNORECASE,
    ), f"Trait suggestion guidance missing in context: {context_text}"
