import pytest
from pmm.directives.detector import extract


def _contents(items):
    # Helper: project to content text for simpler assertions
    return [c.content for c in items]


def test_from_now_on_single():
    text = "From now on, link evidence before closing commitments."
    out = list(extract(text, source="reply", origin_eid=123))
    assert len(out) == 1
    assert out[0].source == "reply"
    assert out[0].origin_eid == 123
    assert out[0].content == "link evidence before closing commitments."


def test_always_and_never_patterns():
    text = "Always strip boilerplate. Never claim an identity unless adopted."
    out = list(extract(text, source="reflection", origin_eid=None))
    # Pattern order: "Always ..." then "Never ..."
    assert _contents(out) == [
        "strip boilerplate.",
        "claim an identity unless adopted.",
    ]
    assert all(c.source == "reflection" for c in out)


def test_directive_label_and_dedup():
    text = (
        "Directive: use evidence_candidate before commitment_close. From now on, "
        "use evidence_candidate before commitment_close."
    )
    out = list(extract(text, source="reply", origin_eid=7))
    # Same directive appears twice via two patterns → dedup to one
    assert len(out) == 1
    assert out[0].content == "use evidence_candidate before commitment_close."
    assert out[0].source == "reply"
    assert out[0].origin_eid == 7


@pytest.mark.parametrize(
    "raw,expected",
    [
        (
            "From now on,   compress   whitespace   inside   text",
            "compress whitespace inside text",
        ),
        ("Directive: keep replies concise", "keep replies concise"),
    ],
)
def test_normalization_whitespace(raw, expected):
    out = list(extract(raw, source="reply", origin_eid=None))
    assert len(out) == 1
    assert out[0].content == expected
