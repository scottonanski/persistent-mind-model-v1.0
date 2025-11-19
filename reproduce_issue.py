from pmm.core.event_log import EventLog
from pmm.runtime.autonomy_kernel import AutonomyKernel
from pmm.runtime.loop import RuntimeLoop
from pmm.adapters.dummy_adapter import DummyAdapter


def test_repro():
    log = EventLog(":memory:")
    kernel = AutonomyKernel(log)

    loop = RuntimeLoop(
        eventlog=log, adapter=DummyAdapter(), replay=False, autonomy=False
    )

    # Generate enough events to meet checkpoint threshold and create selections
    print("Generating events...")
    for i in range(60):
        loop.run_turn("policy enforcement turn")
        # Autonomy maintenance each cycle
        kernel.decide_next_action()

    print("Events generated.")
    events = log.read_all()

    # Selections recorded
    sels = [e for e in events if e.get("kind") == "retrieval_selection"]
    print(f"Found {len(sels)} retrieval_selection events.")

    # Force a verification pass
    print("Forcing verification pass...")
    kernel._verify_recent_selections(N=5)

    events = log.read_all()
    reflections = [e for e in events if e.get("kind") == "reflection"]
    print(f"Found {len(reflections)} reflection events.")

    for r in reflections:
        content = r.get("content", "")
        print(f"Reflection content: {content}")


if __name__ == "__main__":
    test_repro()
