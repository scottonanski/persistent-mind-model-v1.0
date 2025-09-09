from pmm.storage.eventlog import EventLog
from pmm.llm.factory import LLMConfig
from pmm.runtime.loop import Runtime
from pmm.runtime.invariants import check_invariants


def test_runtime_uses_same_chat_for_both_paths(monkeypatch, tmp_path):
    db = tmp_path / "db.sqlite"
    log = EventLog(str(db))
    cfg = LLMConfig(
        provider="openai", model="gpt-4o", embed_provider=None, embed_model=None
    )
    rt = Runtime(cfg, log)

    counters = {"calls": 0}

    def fake_generate(msgs, **kw):
        counters["calls"] += 1
        return f"ok{counters['calls']}"

    monkeypatch.setattr(rt.chat, "generate", fake_generate)

    r1 = rt.handle_user("hi")
    r2 = rt.reflect("ctx")

    assert r1 == "ok1" and r2 == "ok2"
    events = log.read_all()
    assert [e["kind"] for e in events][-2:] == ["response", "reflection"]
    assert counters["calls"] == 2


def test_bridge_pass_through(monkeypatch, tmp_path):
    db = tmp_path / "db.sqlite"
    log = EventLog(str(db))
    cfg = LLMConfig(
        provider="openai", model="gpt-4o", embed_provider=None, embed_model=None
    )
    rt = Runtime(cfg, log)

    seen = {}

    def spy_generate(msgs, **kw):
        seen["msgs"] = msgs
        return "ok"

    monkeypatch.setattr(rt.chat, "generate", spy_generate)
    _ = rt.handle_user("hello")

    assert isinstance(seen["msgs"], list)
    assert seen["msgs"][0]["content"] == "hello"


def _mk_ev(id_: int, kind: str, content: str = "", meta: dict | None = None):
    return {
        "id": id_,
        "ts": f"2025-01-01T00:00:{id_:02d}Z",
        "kind": kind,
        "content": content,
        "meta": meta or {},
    }


def test_identity_idempotent_proposals_and_sanitized_adopt():
    evs = []
    evs.append(_mk_ev(1, "identity_propose", content="Ada"))
    evs.append(
        _mk_ev(2, "identity_propose", content="Ada2")
    )  # back-to-back proposals violate policy
    evs.append(
        _mk_ev(3, "identity_adopt", content="Ada", meta={"name": "Ada", "tick": 3})
    )
    v = check_invariants(evs)
    assert "identity:multiple_proposals_without_adopt" in v
    # Fix by placing adopt between proposals
    evs2 = []
    evs2.append(_mk_ev(1, "identity_propose", content="Ada"))
    evs2.append(
        _mk_ev(2, "identity_adopt", content="Ada", meta={"name": "Ada", "tick": 2})
    )
    evs2.append(_mk_ev(3, "identity_propose", content="Zoe"))
    v2 = check_invariants(evs2)
    assert "identity:multiple_proposals_without_adopt" not in v2
    assert "identity:adopted_name_invalid" not in v2


def test_one_shot_renderer_order_is_consistent():
    # adopt then responses; invariant ensures there is a first response after adopt
    evs = []
    evs.append(
        _mk_ev(1, "identity_adopt", content="Ada", meta={"name": "Ada", "tick": 1})
    )
    evs.append(_mk_ev(2, "response", content="Hello"))
    evs.append(_mk_ev(3, "response", content="Next"))
    v = check_invariants(evs)
    assert "renderer:missing_first_response_after_adopt" not in v


def test_commitment_close_exact_match_only_invariants():
    # open Ada and Adam; close only Ada on adopt Ada
    evs = []
    evs.append(
        _mk_ev(1, "commitment_open", meta={"cid": "c1", "text": "identity:name:Ada"})
    )
    evs.append(
        _mk_ev(2, "commitment_open", meta={"cid": "c2", "text": "identity:name:Adam"})
    )
    evs.append(
        _mk_ev(3, "identity_adopt", content="Ada", meta={"name": "Ada", "tick": 3})
    )
    # First response after adopt (satisfy renderer invariant)
    evs.append(_mk_ev(4, "response", content="Hi"))
    evs.append(
        _mk_ev(
            5, "commitment_close", meta={"cid": "c1", "description": "adopted name Ada"}
        )
    )
    v = check_invariants(evs)
    assert "commitments:closed_non_exact_identity_name" not in v
    # If Adam is closed for Ada, violation
    evs_bad = list(evs)
    evs_bad.append(
        _mk_ev(
            6, "commitment_close", meta={"cid": "c2", "description": "adopted name Ada"}
        )
    )
    vbad = check_invariants(evs_bad)
    assert "commitments:closed_non_exact_identity_name" in vbad


def test_trait_update_rate_limits_and_gating_invariants():
    # trait updates before adopt -> violation
    evs = []
    evs.append(
        _mk_ev(
            1,
            "trait_update",
            meta={
                "trait": "openness",
                "delta": 0.02,
                "reason": "novelty_push",
                "tick": 1,
            },
        )
    )
    evs.append(
        _mk_ev(2, "identity_adopt", content="Ada", meta={"name": "Ada", "tick": 2})
    )
    v = check_invariants(evs)
    assert "drift:trait_update_before_adopt" in v
    # Rate limit violation: two same-reason updates <5 ticks apart
    evs2 = []
    evs2.append(
        _mk_ev(1, "identity_adopt", content="Ada", meta={"name": "Ada", "tick": 1})
    )
    evs2.append(
        _mk_ev(
            2,
            "trait_update",
            meta={
                "trait": "openness",
                "delta": 0.02,
                "reason": "novelty_push",
                "tick": 5,
            },
        )
    )
    evs2.append(
        _mk_ev(
            3,
            "trait_update",
            meta={
                "trait": "openness",
                "delta": 0.02,
                "reason": "novelty_push",
                "tick": 8,
            },
        )
    )
    v2 = check_invariants(evs2)
    assert "drift:rate_limit_violation" in v2
    # Fix spacing
    evs3 = []
    evs3.append(
        _mk_ev(1, "identity_adopt", content="Ada", meta={"name": "Ada", "tick": 1})
    )
    evs3.append(
        _mk_ev(
            2,
            "trait_update",
            meta={
                "trait": "openness",
                "delta": 0.02,
                "reason": "novelty_push",
                "tick": 5,
            },
        )
    )
    evs3.append(
        _mk_ev(
            3,
            "trait_update",
            meta={
                "trait": "openness",
                "delta": 0.02,
                "reason": "novelty_push",
                "tick": 10,
            },
        )
    )
    v3 = check_invariants(evs3)
    assert "drift:rate_limit_violation" not in v3


def test_ledger_monotonic_ids_and_meta_shape():
    # Non-monotonic id and non-dict meta cause violations
    evs = []
    evs.append(_mk_ev(2, "response"))
    evs.append(_mk_ev(1, "response"))  # non-monotonic
    evs.append(
        {"id": 3, "ts": "", "kind": 123, "content": "", "meta": {}}
    )  # kind not string
    evs.append(
        {"id": 4, "ts": "", "kind": "response", "content": "", "meta": []}
    )  # meta not dict
    v = check_invariants(evs)
    assert "ledger:non_monotonic_id" in v
    assert "ledger:kind_not_string" in v
    assert "ledger:meta_not_dict" in v
