import json
from pmm.core.event_log import EventLog
from pmm.runtime.autonomy_kernel import AutonomyKernel
from pmm.runtime.loop import RuntimeLoop
from pmm.adapters.dummy_adapter import DummyAdapter
from pmm.retrieval.vector import (
    DeterministicEmbedder,
    cosine,
    build_index,
    candidate_messages,
)


def check_mismatch():
    log = EventLog(":memory:")
    kernel = AutonomyKernel(log)
    loop = RuntimeLoop(
        eventlog=log, adapter=DummyAdapter(), replay=False, autonomy=False
    )

    # Generate events
    for i in range(10):
        loop.run_turn(f"policy enforcement turn {i}")
        kernel.decide_next_action()

    events = log.read_all()
    sels = [e for e in events if e.get("kind") == "retrieval_selection"]
    last_sel = sels[-1]

    data = json.loads(last_sel.get("content") or "{}")
    turn_id = int(data.get("turn_id", 0))
    selected = data.get("selected") or []

    model = "hash64"
    dims = 64

    # Reconstruct query
    query = ""
    for e in reversed(events):
        if int(e.get("id", 0)) >= turn_id:
            continue
        if e.get("kind") == "user_message":
            query = e.get("content") or ""
            break

    print(f"Query: {query}")

    # Method A: Full Precision (RuntimeLoop style)
    embedder = DeterministicEmbedder(model=model, dims=dims)
    qv = embedder.embed(query)
    cands = candidate_messages(events, up_to_id=turn_id)

    scored_full = []
    for ev in cands:
        eid = int(ev.get("id", 0))
        v = embedder.embed(ev.get("content") or "")
        s = cosine(qv, v)
        scored_full.append((eid, s))
    scored_full.sort(key=lambda t: (-t[1], t[0]))

    top_full = [eid for (eid, s) in scored_full[:5]]
    print(f"Top 5 Full Precision: {top_full}")
    print(f"Scores Full: {[s for (eid, s) in scored_full[:5]]}")

    # Method B: Quantized (AutonomyKernel style)
    idx = build_index(events, model=model, dims=dims)
    scored_quant = []
    for ev in cands:
        eid = int(ev.get("id", 0))
        vec = idx.get(eid)
        if vec is None:
            vec = embedder.embed(ev.get("content") or "")
        s = cosine(qv, vec)
        scored_quant.append((eid, s))
    scored_quant.sort(key=lambda t: (-t[1], t[0]))

    top_quant = [eid for (eid, s) in scored_quant[:5]]
    print(f"Top 5 Quantized: {top_quant}")
    print(f"Scores Quant: {[s for (eid, s) in scored_quant[:5]]}")

    print(f"Selected: {selected}")

    overlap_full = set(top_full).intersection(set(selected))
    overlap_quant = set(top_quant).intersection(set(selected))

    print(f"Overlap Full: {overlap_full}")
    print(f"Overlap Quant: {overlap_quant}")


if __name__ == "__main__":
    check_mismatch()
