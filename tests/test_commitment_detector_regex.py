from pmm.commitments.detectors import detect_commitments


def test_detect_commitments_is_deterministic_and_deduped():
    text = "I'll draft the summary. I will send the email. TODO: clean up docs. Let's review the PR."
    cands = detect_commitments(text, source="reply")
    outs = [c.text.lower() for c in cands]
    assert outs[0].startswith("draft the summary")
    assert "send the email" in outs[1]
    assert any("clean up docs" in x for x in outs)
    assert any("review the pr" in x for x in outs)

    # de-dup within one call
    text2 = "I will send the email. I'll send the email."
    outs2 = [c.text for c in detect_commitments(text2)]
    assert outs2.count("send the email") == 1
