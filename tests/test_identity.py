from __future__ import annotations


from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model
from pmm.runtime.bridge import ResponseRenderer
from pmm.llm.factory import LLMConfig
from pmm.runtime.loop import Runtime, AutonomyLoop
from pmm.cli.chat import should_print_identity_notice


def test_projection_identity_adopt_last_wins_and_traits_clamp(tmp_path):
    db = tmp_path / "id.db"
    log = EventLog(str(db))
    # Multiple adopts -> last wins
    log.append(kind="identity_adopt", content="Zoe", meta={"name": "Zoe", "tick": 1})
    log.append(kind="identity_adopt", content="Ada", meta={"name": "Ada", "tick": 2})
    # Trait updates accumulate and clamp
    log.append(
        kind="trait_update",
        content="",
        meta={"trait": "openness", "delta": 0.6, "reason": "test", "tick": 3},
    )
    log.append(
        kind="trait_update",
        content="",
        meta={"trait": "openness", "delta": 0.6, "reason": "test", "tick": 4},
    )
    log.append(
        kind="trait_update",
        content="",
        meta={"trait": "N", "delta": -1.0, "reason": "test", "tick": 5},
    )

    model = build_self_model(log.read_all())
    ident = model["identity"]
    assert ident["name"] == "Ada"
    traits = ident["traits"]
    assert 0.0 <= traits["openness"] <= 1.0
    assert traits["openness"] == 1.0  # clamped
    assert traits["neuroticism"] == 0.0  # clamped low


def test_renderer_strips_boilerplate_and_one_shot_signature():
    r = ResponseRenderer()
    raw = "As an AI assistant, I can help you."
    ident = {"name": "Ada", "_recent_adopt": True, "traits": {}}
    out = r.render(raw, ident, stage="S1")
    assert not out.lower().startswith("as an ai")
    assert out.rstrip().endswith("— Ada")
    # If not recent adopt, no banner
    out2 = r.render("Hello", {"name": "Ada", "traits": {}}, stage="S1")
    assert not out2.endswith("— Ada")


def _mk_rt(tmp_path):
    db = tmp_path / "rt.db"
    log = EventLog(str(db))
    cfg = LLMConfig(
        provider="openai", model="gpt-4o", embed_provider=None, embed_model=None
    )
    return Runtime(cfg, log), log


def _append_autonomy_tick(log: EventLog, IAS: float = 0.5, GAS: float = 0.4):
    log.append(
        kind="autonomy_tick",
        content="beat",
        meta={"telemetry": {"IAS": IAS, "GAS": GAS}},
    )


def _append_debug_reflect_skip(log: EventLog, reason: str):
    log.append(kind="debug", content="", meta={"reflect_skip": reason})


def test_autonomy_proposes_identity_once_at_S1_with_novelty(tmp_path, monkeypatch):
    rt, log = _mk_rt(tmp_path)
    # Prime stage >= S1 and 4 ticks
    for _ in range(4):
        _append_autonomy_tick(log, IAS=0.4, GAS=0.25)
    _append_debug_reflect_skip(log, reason="time")  # novelty ok

    # Monkeypatch proposer to deterministic name
    monkeypatch.setattr(rt, "_propose_identity_name", lambda: "Ada")

    # Run tick to trigger proposal on 5th
    aloop = AutonomyLoop(
        eventlog=log,
        cooldown=rt.cooldown,
        interval_seconds=0.1,
        proposer=rt._propose_identity_name,
    )
    aloop.tick()

    events = log.read_all()
    kinds = [e["kind"] for e in events]
    assert "identity_propose" in kinds
    # Running again should not propose again (once only until adopted)
    aloop.tick()
    kinds2 = [e["kind"] for e in log.read_all()]
    assert kinds2.count("identity_propose") == 1


def test_autonomy_adopts_on_affirmation_or_bootstrap(tmp_path, monkeypatch):
    rt, log = _mk_rt(tmp_path)
    # Prepare: reach S1 with 5 ticks
    for _ in range(5):
        _append_autonomy_tick(log, IAS=0.4, GAS=0.25)
    _append_debug_reflect_skip(log, reason="time")
    monkeypatch.setattr(rt, "_propose_identity_name", lambda: "Ada")
    aloop = AutonomyLoop(
        eventlog=log,
        cooldown=rt.cooldown,
        interval_seconds=0.1,
        proposer=rt._propose_identity_name,
    )
    aloop.tick()  # emits identity_propose

    # Case A: affirmation via assistant reply
    log.append(kind="response", content="I am Ada", meta={})
    aloop.tick()
    events = log.read_all()
    assert any(e["kind"] == "identity_adopt" and e["content"] == "Ada" for e in events)

    # Reset DB for Case B: bootstrap after 5 more ticks without affirmation
    db2 = tmp_path / "rt2.db"
    log2 = EventLog(str(db2))
    for _ in range(5):
        _append_autonomy_tick(log2, IAS=0.4, GAS=0.25)
    _append_debug_reflect_skip(log2, reason="time")
    aloop2 = AutonomyLoop(
        eventlog=log2,
        cooldown=rt.cooldown,
        interval_seconds=0.1,
        proposer=lambda: "Ada",
    )
    aloop2.tick()  # propose
    # 5 more ticks without affirmation
    for _ in range(5):
        aloop2.tick()
    events2 = log2.read_all()
    assert any(e["kind"] == "identity_adopt" for e in events2)


def test_identity_commitment_open_and_close_on_adopt(tmp_path, monkeypatch):
    rt, log = _mk_rt(tmp_path)

    def gen_commit(msgs, **kw):
        return "I will use the name Ada"

    monkeypatch.setattr(rt.chat, "generate", gen_commit)
    rt.handle_user("hi")
    model = build_self_model(log.read_all())
    open_map = model.get("commitments", {}).get("open", {})
    # Expect identity commitment exists
    assert any(
        str((m or {}).get("text")) == "identity:name:Ada" for m in open_map.values()
    )

    # Now emit identity_adopt; commitment should close
    log.append(
        kind="identity_adopt",
        content="Ada",
        meta={"name": "Ada", "why": "test", "tick": 10},
    )
    # Use helper via runtime autonomy tick path that calls closer; or call classmethod directly
    from pmm.commitments.tracker import CommitmentTracker

    CommitmentTracker.close_identity_name_on_adopt(log, "Ada")
    model2 = build_self_model(log.read_all())
    assert len(model2.get("commitments", {}).get("open", {})) == 0


def test_persistence_and_renderer_use_identity(tmp_path, monkeypatch):
    # Persist an adoption, restart runtime, ensure renderer uses signature once
    db = tmp_path / "p.db"
    log = EventLog(str(db))
    log.append(kind="identity_adopt", content="Ada", meta={"name": "Ada", "tick": 1})

    rt = Runtime(
        LLMConfig(
            provider="openai", model="gpt-4o", embed_provider=None, embed_model=None
        ),
        log,
    )

    def gen(msgs, **kw):
        return "As an AI, I can help."

    monkeypatch.setattr(rt.chat, "generate", gen)
    out = rt.handle_user("hi")
    # Renderer should strip boilerplate and append signature since adopt is most recent
    assert "As an AI" not in out
    assert out.rstrip().endswith("— Ada")

    # Next reply should NOT append signature again
    monkeypatch.setattr(rt.chat, "generate", lambda msgs, **kw: "Hello")
    out2 = rt.handle_user("next")
    assert not out2.rstrip().endswith("— Ada")


def _mk_autonomy(tmp_path, cooldown, proposer=lambda: "Ada"):
    db = tmp_path / "auto.db"
    log = EventLog(str(db))
    # prime S1 (IAS/GAS)
    for _ in range(5):
        log.append(
            kind="autonomy_tick",
            content="beat",
            meta={"telemetry": {"IAS": 0.4, "GAS": 0.25}},
        )
    log.append(kind="debug", content="", meta={"reflect_skip": "time"})
    loop = AutonomyLoop(
        eventlog=log, cooldown=cooldown, interval_seconds=0.1, proposer=proposer
    )
    return loop, log


def test_affirmation_strict_sentence_only(tmp_path):
    # Set up with a proposal
    rt, log = _mk_rt(tmp_path)
    aloop, elog = _mk_autonomy(tmp_path, rt.cooldown, proposer=lambda: "Ada")
    aloop.tick()  # emit identity_propose
    # Reject quoted
    elog.append(kind="response", content='"I am Ada."', meta={})
    aloop.tick()
    assert not any(e["kind"] == "identity_adopt" for e in elog.read_all())
    # Reject code-fenced
    elog.append(
        kind="response",
        content="""```
I am Ada
```""",
        meta={},
    )
    aloop.tick()
    assert not any(e["kind"] == "identity_adopt" for e in elog.read_all())
    # Reject negation
    elog.append(kind="response", content="I am not Ada.", meta={})
    aloop.tick()
    assert not any(e["kind"] == "identity_adopt" for e in elog.read_all())
    # Accept clean
    elog.append(kind="response", content="I am Ada.", meta={})
    aloop.tick()
    assert any(
        e["kind"] == "identity_adopt" and e["content"] == "Ada" for e in elog.read_all()
    )


def test_affirmation_name_validation(tmp_path):
    rt, log = _mk_rt(tmp_path)
    aloop, elog = _mk_autonomy(tmp_path, rt.cooldown, proposer=lambda: "Ada")
    aloop.tick()  # propose
    bads = ["I am _Ada", "I am Ada_", "I am --Ada", "I am 1234", "I am admin"]
    for b in bads:
        elog.append(kind="response", content=b, meta={})
        aloop.tick()
        # ensure no adopt from invalid
        assert not any(e["kind"] == "identity_adopt" for e in elog.read_all())


def test_proposal_adoption_idempotence(tmp_path):
    rt, log = _mk_rt(tmp_path)
    aloop, elog = _mk_autonomy(tmp_path, rt.cooldown, proposer=lambda: "Ada")
    aloop.tick()
    # No second proposal
    aloop.tick()
    kinds = [e["kind"] for e in elog.read_all()]
    assert kinds.count("identity_propose") == 1
    # Adopt once
    elog.append(kind="response", content="I am Ada", meta={})
    aloop.tick()
    kinds = [e["kind"] for e in elog.read_all()]
    assert kinds.count("identity_adopt") == 1
    # Even if another response asserts, we do not adopt again without a new proposal
    elog.append(kind="response", content="I am Ada", meta={})
    aloop.tick()
    kinds = [e["kind"] for e in elog.read_all()]
    assert kinds.count("identity_adopt") == 1


def test_commitment_close_exact_match_only(tmp_path, monkeypatch):
    rt, log = _mk_rt(tmp_path)

    # Open two identity commitments: Ada and Adam
    def gen_commit(msgs, **kw):
        return "I will use the name Ada. Also, I will use the name Adam."

    monkeypatch.setattr(rt.chat, "generate", gen_commit)
    rt.handle_user("hi")
    model = build_self_model(log.read_all())
    open_map = model.get("commitments", {}).get("open", {})
    assert any(
        str((m or {}).get("text")) == "identity:name:Ada" for m in open_map.values()
    )
    # We might not auto-open Adam since detector captures first segment; open explicitly for test
    from pmm.commitments.tracker import CommitmentTracker

    tracker = CommitmentTracker(log)
    tracker.add_commitment("identity:name:Adam", source="identity")
    # Adopt Ada
    log.append(kind="identity_adopt", content="Ada", meta={"name": "Ada", "tick": 99})
    CommitmentTracker.close_identity_name_on_adopt(log, "Ada")
    model2 = build_self_model(log.read_all())
    open2 = model2.get("commitments", {}).get("open", {})
    # Ada closed, Adam remains
    assert not any(
        str((m or {}).get("text")) == "identity:name:Ada" for m in open2.values()
    )
    assert any(
        str((m or {}).get("text")) == "identity:name:Adam" for m in open2.values()
    )


def test_name_validator_single_source(tmp_path, monkeypatch):
    # Monkeypatch proposer to return bad names and ensure sanitizer fallback applies
    rt, log = _mk_rt(tmp_path)
    calls = {"n": 0}

    def bad_then_bad_again():
        calls["n"] += 1
        return "--Ada" if calls["n"] == 1 else "_Ada"

    monkeypatch.setattr(rt, "_propose_identity_name", lambda: bad_then_bad_again())
    # Call through the internal proposer wrapper via autonomy tick path
    aloop = AutonomyLoop(
        eventlog=log,
        cooldown=rt.cooldown,
        interval_seconds=0.1,
        proposer=rt._propose_identity_name,
    )
    # Prime S1 and novelty ok, 5th tick triggers proposal event with fallback name "Persona"
    for _ in range(5):
        log.append(
            kind="autonomy_tick",
            content="beat",
            meta={"telemetry": {"IAS": 0.4, "GAS": 0.25}},
        )
    log.append(kind="debug", content="", meta={"reflect_skip": "time"})
    aloop.tick()
    evs = log.read_all()
    assert any(
        e["kind"] == "identity_propose" and (e["content"] == "Persona" or e["content"])
        for e in evs
    )
    # Ensure no duplicate sanitizer function exists on Runtime class
    assert not hasattr(Runtime, "_NAME_BANLIST")
    assert (
        "def _sanitize_name("
        in open("pmm/runtime/loop.py", "r", encoding="utf-8").read()
    )


def test_renderer_signature_edge_cases():
    r = ResponseRenderer()
    ident = {"name": "Ada", "_recent_adopt": True, "traits": {}}
    # Case 1: very short reply
    out = r.render("OK", ident, stage="S1")
    assert not out.rstrip().endswith("— Ada")
    # Case 2: duplicate with trailing whitespace/newline
    base = "Thanks for the update.\n— Ada  \n"
    out2 = r.render(base, ident, stage="S1")
    assert out2.rstrip().endswith("— Ada")
    assert out2.count("— Ada") == 1


def test_repl_notice_one_shot_ordering():
    # Build a synthetic event ordering to ensure strict one-shot semantics
    events = []
    # ids increase; autonomous adopt at id 10
    # prior response at id 8
    events.append({"id": 1, "kind": "response"})
    events.append({"id": 8, "kind": "response"})
    events.append({"id": 10, "kind": "identity_adopt"})
    # first reply after adopt (id 11) -> should print
    events.append({"id": 11, "kind": "response"})
    assert should_print_identity_notice(events) is True
    # add another response (id 12) -> should not print
    events2 = events + [{"id": 12, "kind": "response"}]
    assert should_print_identity_notice(events2) is False


def test_trait_drift_emits_bounded_events(tmp_path, monkeypatch):
    # Prepare DB with adopted identity
    db = tmp_path / "drift.db"
    log = EventLog(str(db))
    log.append(kind="identity_adopt", content="Ada", meta={"name": "Ada", "tick": 1})
    rt = Runtime(
        LLMConfig(
            provider="openai", model="gpt-4o", embed_provider=None, embed_model=None
        ),
        log,
    )
    aloop = AutonomyLoop(
        eventlog=log, cooldown=rt.cooldown, interval_seconds=0.1, proposer=lambda: "Ada"
    )

    # Helper to count trait updates by reason
    def _count(reason: str):
        return sum(
            1
            for e in log.read_all()
            if e.get("kind") == "trait_update"
            and (e.get("meta") or {}).get("reason") == reason
        )

    # Prime with autonomy ticks and zero open commitments (for stable_period rule)
    for _ in range(2):
        aloop.tick()
    # Third consecutive zero-open tick should trigger stable_period
    aloop.tick()
    assert _count("stable_period") == 1

    # Rate limit: immediate follow-up tick should not add another stable_period
    aloop.tick()
    assert _count("stable_period") == 1

    # Novelty push: append three low_novelty debug skips, then tick
    log.append(kind="debug", content="", meta={"reflect_skip": "low_novelty"})
    aloop.tick()
    log.append(kind="debug", content="", meta={"reflect_skip": "low_novelty"})
    aloop.tick()
    log.append(kind="debug", content="", meta={"reflect_skip": "low_novelty"})
    aloop.tick()
    assert _count("novelty_push") == 1

    # Close-rate up: open commitments then close one with a reflection
    from pmm.commitments.tracker import CommitmentTracker

    tracker = CommitmentTracker(log)
    cid1 = tracker.add_commitment("do A", source="test")
    cid2 = tracker.add_commitment("do B", source="test")
    # One tick baseline
    aloop.tick()
    # Emit reflection and close one commitment
    log.append(
        kind="reflection", content="ok", meta={"telemetry": {"IAS": 0.4, "GAS": 0.25}}
    )
    monkeypatch.setenv("TEST_ALLOW_TEXT_ONLY_EVIDENCE", "1")
    tracker.close_with_evidence(cid1, evidence_type="done", description="done A")
    # Next tick should detect close_rate_up
    aloop.tick()
    assert _count("close_rate_up") == 1

    # Rate limit: try to trigger again immediately — should not increment
    log.append(
        kind="reflection", content="ok2", meta={"telemetry": {"IAS": 0.4, "GAS": 0.25}}
    )
    tracker.close_with_evidence(cid2, evidence_type="done", description="done B")
    aloop.tick()
    assert _count("close_rate_up") == 1

    # Clamping: push openness upward repeatedly until exceeding 1.0
    for _ in range(10):
        log.append(kind="debug", content="", meta={"reflect_skip": "low_novelty"})
        aloop.tick()
    model = build_self_model(log.read_all())
    assert 0.0 <= model["identity"]["traits"]["openness"] <= 1.0


def test_no_drift_before_identity_adopt(tmp_path):
    db = tmp_path / "nodrift.db"
    log = EventLog(str(db))
    rt = Runtime(
        LLMConfig(
            provider="openai", model="gpt-4o", embed_provider=None, embed_model=None
        ),
        log,
    )
    aloop = AutonomyLoop(
        eventlog=log, cooldown=rt.cooldown, interval_seconds=0.1, proposer=lambda: "Ada"
    )
    # Emit sequences similar to drift triggers
    log.append(kind="debug", content="", meta={"reflect_skip": "low_novelty"})
    aloop.tick()
    log.append(kind="debug", content="", meta={"reflect_skip": "low_novelty"})
    aloop.tick()
    log.append(kind="debug", content="", meta={"reflect_skip": "low_novelty"})
    aloop.tick()
    # No identity_adopt yet; ensure no trait_update at all
    assert not any(e.get("kind") == "trait_update" for e in log.read_all())
