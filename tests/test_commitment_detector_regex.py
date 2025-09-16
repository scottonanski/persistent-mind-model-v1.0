from pmm.commitments.detectors import detect_commitments


def test_detect_commitments_is_disabled():
    text = "I'll draft the summary. I will send the email. TODO: clean up docs. Let's review the PR."
    cands = detect_commitments(text, source="reply")
    assert cands == []
