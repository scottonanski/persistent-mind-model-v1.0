from __future__ import annotations


def test_autonomy_loop_import_stable():
    # Verify the staged extraction path exists and resolves
    from pmm.runtime import loop as loop_mod
    from pmm.runtime.autonomy_loop import AutonomyLoop

    # Ensure the class object is consistent with the legacy location
    assert hasattr(loop_mod, "AutonomyLoop")
    assert AutonomyLoop is loop_mod.AutonomyLoop
