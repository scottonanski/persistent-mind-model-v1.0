from pmm.directives.detector import extract as _extract


def test_runtime_emits_directives_after_reply_like_snippet():
    appended = []

    class FakeEventLog:
        def append(self, *, kind: str, content: str = "", meta: dict | None = None):
            ev = {"kind": kind, "content": content, "meta": meta or {}}
            appended.append(ev)
            return len(appended)

    log = FakeEventLog()
    reply_eid = 100
    reply_text = "Directive: keep replies concise."

    # This mirrors the snippet integrated in Runtime.handle_user after response append
    for cand in _extract(reply_text, source="reply", origin_eid=reply_eid):
        log.append(
            kind="autonomy_directive",
            content=str(cand.content),
            meta={"source": str(cand.source), "origin_eid": cand.origin_eid},
        )

    assert len(appended) >= 1
    ev = appended[-1]
    assert ev["kind"] == "autonomy_directive"
    assert ev["content"] == "keep replies concise."
    assert ev["meta"]["source"] == "reply"
    assert ev["meta"]["origin_eid"] == 100
