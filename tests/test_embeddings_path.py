from pmm.commitments.tracker import CommitmentTracker
from pmm.llm.factory import LLMConfig
from pmm.runtime.loop import Runtime
from pmm.runtime.recall import suggest_recall
from pmm.storage.eventlog import EventLog


class _DummyChat:
    def generate(self, messages, temperature=0.0, max_tokens=64):
        # Return a deterministic short reply
        return "Acknowledged."


class _DummyBundle:
    def __init__(self):
        self.chat = _DummyChat()


def _runtime_with_dummy_chat(tmp_path):
    log = EventLog(str(tmp_path / "embeds.db"))
    cfg = LLMConfig(provider="openai", model="gpt-4o")
    rt = Runtime(cfg, log)
    # Monkeypatch the chat adapter to avoid any external calls
    rt.chat = _DummyChat()
    return rt, log


def test_embedding_indexed_event(tmp_path, monkeypatch):
    rt, log = _runtime_with_dummy_chat(tmp_path)
    _ = rt.handle_user("Hi")
    events = log.read_all()
    kinds = [e.get("kind") for e in events]
    assert "embedding_indexed" in kinds
    # Ensure eid is prior and digest exists
    emb = next(e for e in events if e.get("kind") == "embedding_indexed")
    eid = (emb.get("meta") or {}).get("eid")
    assert isinstance(eid, int) and eid > 0
    # eid must point to a prior event id
    assert any(ev.get("id") == eid for ev in events if ev.get("id") < emb.get("id"))
    assert (emb.get("meta") or {}).get("digest")


def test_embedding_always_indexed(tmp_path, monkeypatch):
    rt, log = _runtime_with_dummy_chat(tmp_path)
    _ = rt.handle_user("Hello")
    kinds = [e.get("kind") for e in log.read_all()]
    assert "embedding_indexed" in kinds


def test_recall_prefers_embeddings(tmp_path, monkeypatch):

    log = EventLog(str(tmp_path / "recall.db"))
    # Create two prior events
    id1 = log.append(kind="response", content="foo bar baz", meta={})
    log.append(kind="response", content="unrelated text", meta={})

    # Current text similar to first
    current = "foo baz"
    suggestions = suggest_recall(log.read_all(), current, max_items=1)
    assert suggestions and suggestions[0]["eid"] == id1


def test_evidence_prefers_embeddings(tmp_path, monkeypatch):

    log = EventLog(str(tmp_path / "evidence.db"))
    ct = CommitmentTracker(log)

    # Open a commitment related to "write the report"
    cid = ct.add_commitment(
        "write the report", source="test", extra_meta={"reason": "reflection"}
    )
    assert cid

    # Provide a Done line that should be similar by embeddings
    ct.close_reflection_on_next("finished the report yesterday.")
    # New method directly emits commitment_close without evidence_candidate
    events = log.read_all()
    kinds = [e.get("kind") for e in events]
    assert (
        "evidence_candidate" not in kinds
    )  # No evidence_candidate with new implementation
    assert "commitment_close" in kinds  # Direct close still happens
