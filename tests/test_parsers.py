"""
Unit tests for pmm.utils.parsers - deterministic text parsing.

These tests verify that all parsing functions work correctly without regex.
"""

from pmm.utils.parsers import (
    extract_commitment_claims,
    extract_event_ids,
    extract_first_sentence,
    extract_name_from_change_event,
    is_iso_timestamp,
    normalize_whitespace,
    parse_commitment_refs,
    split_key_value,
    strip_markdown_formatting,
    token_overlap_ratio,
    tokenize_alphanumeric,
)


class TestExtractEventIds:
    """Test event ID extraction without regex."""

    def test_simple_event_reference(self):
        assert extract_event_ids("event 123") == [123]
        assert extract_event_ids("Event 456") == [456]
        assert extract_event_ids("EVENT 789") == [789]

    def test_id_colon_format(self):
        assert extract_event_ids("ID: 100") == [100]
        assert extract_event_ids("id: 200") == [200]
        assert extract_event_ids("ID:300") == [300]

    def test_multiple_events(self):
        text = "event 1 and event 2 and ID: 3"
        assert extract_event_ids(text) == [1, 2, 3]

    def test_iso_timestamp_not_matched(self):
        """Critical: ISO timestamps should NOT be parsed as event IDs."""
        text = "Event 2025-10-02T18:17:58Z"
        assert extract_event_ids(text) == []

    def test_date_not_matched(self):
        text = "Event 2025-10-02"
        assert extract_event_ids(text) == []

    def test_commitment_format_not_matched(self):
        """Commitment format like '562:bab3a368' should not be event ID."""
        text = "commitment 562:bab3a368"
        assert extract_event_ids(text) == []

    def test_standalone_number_not_matched(self):
        """Standalone numbers without 'event' or 'id' prefix should not match."""
        text = "There are 42 items"
        assert extract_event_ids(text) == []

    def test_empty_input(self):
        assert extract_event_ids("") == []
        assert extract_event_ids(None) == []

    def test_deduplication(self):
        text = "event 5 and event 5 again"
        assert extract_event_ids(text) == [5]

    def test_sorted_output(self):
        text = "event 100 and event 50 and event 75"
        assert extract_event_ids(text) == [50, 75, 100]


class TestParseCommitmentRefs:
    """Test commitment reference extraction."""

    def test_event_cid_format(self):
        refs = parse_commitment_refs("commitment 562:bab3a368")
        assert "bab3a368" in refs

    def test_cid_prefix_format(self):
        refs = parse_commitment_refs("CID abc12345")
        assert "abc12345" in refs

    def test_multiple_refs(self):
        text = "123:deadbeef and CID cafebabe"
        refs = parse_commitment_refs(text)
        assert "deadbeef" in refs
        assert "cafebabe" in refs

    def test_invalid_hex_rejected(self):
        refs = parse_commitment_refs("123:notahex")
        assert len(refs) == 0

    def test_too_short_cid_rejected(self):
        refs = parse_commitment_refs("123:abc")
        assert len(refs) == 0

    def test_empty_input(self):
        assert parse_commitment_refs("") == []
        assert parse_commitment_refs(None) == []


class TestIsIsoTimestamp:
    """Test ISO timestamp detection."""

    def test_full_iso_timestamp(self):
        assert is_iso_timestamp("2025-10-02T18:17:58Z") is True
        assert is_iso_timestamp("2025-10-02T18:17:58+00:00") is True

    def test_date_only(self):
        assert is_iso_timestamp("2025-10-02") is True

    def test_not_timestamp(self):
        assert is_iso_timestamp("Event 123") is False
        assert is_iso_timestamp("hello world") is False
        assert is_iso_timestamp("123456") is False

    def test_empty_input(self):
        assert is_iso_timestamp("") is False
        assert is_iso_timestamp(None) is False


class TestSplitKeyValue:
    """Test key-value splitting."""

    def test_simple_split(self):
        assert split_key_value("Name: Alice") == ("Name", "Alice")
        assert split_key_value("Status: open") == ("Status", "open")

    def test_url_with_port(self):
        """Should only split on FIRST colon."""
        key, val = split_key_value("URL: http://example.com:8080")
        assert key == "URL"
        assert val == "http://example.com:8080"

    def test_no_separator(self):
        assert split_key_value("no separator here") == ("", "")

    def test_empty_input(self):
        assert split_key_value("") == ("", "")

    def test_custom_separator(self):
        assert split_key_value("a=b", separator="=") == ("a", "b")


class TestNormalizeWhitespace:
    """Test whitespace normalization."""

    def test_collapse_spaces(self):
        assert normalize_whitespace("hello    world") == "hello world"

    def test_collapse_tabs_newlines(self):
        assert normalize_whitespace("hello\t\nworld") == "hello world"

    def test_trim_edges(self):
        assert normalize_whitespace("  hello  ") == "hello"

    def test_empty_input(self):
        assert normalize_whitespace("") == ""
        assert normalize_whitespace(None) == ""


class TestTokenizeAlphanumeric:
    """Test alphanumeric tokenization."""

    def test_simple_tokens(self):
        tokens = tokenize_alphanumeric("hello world")
        assert tokens == ["hello", "world"]

    def test_preserve_apostrophes(self):
        tokens = tokenize_alphanumeric("don't can't won't")
        assert "don't" in tokens
        assert "can't" in tokens

    def test_remove_punctuation(self):
        tokens = tokenize_alphanumeric("hello, world!")
        assert tokens == ["hello", "world"]

    def test_lowercase(self):
        tokens = tokenize_alphanumeric("Hello WORLD")
        assert tokens == ["hello", "world"]

    def test_empty_input(self):
        assert tokenize_alphanumeric("") == []
        assert tokenize_alphanumeric(None) == []


class TestExtractNameFromChangeEvent:
    """Test name extraction from change events."""

    def test_standard_format(self):
        name = extract_name_from_change_event("Name changed to: Alice")
        assert name == "Alice"

    def test_case_insensitive(self):
        name = extract_name_from_change_event("name changed to: Bob")
        assert name == "Bob"

    def test_no_match(self):
        name = extract_name_from_change_event("Some other text")
        assert name is None

    def test_empty_input(self):
        assert extract_name_from_change_event("") is None
        assert extract_name_from_change_event(None) is None


class TestTokenOverlapRatio:
    """Test token overlap calculation."""

    def test_identical_texts(self):
        ratio = token_overlap_ratio("hello world", "hello world")
        assert ratio == 1.0

    def test_no_overlap(self):
        ratio = token_overlap_ratio("hello world", "foo bar")
        assert ratio == 0.0

    def test_partial_overlap(self):
        ratio = token_overlap_ratio("hello world", "hello universe")
        assert 0.0 < ratio < 1.0

    def test_empty_input(self):
        assert token_overlap_ratio("", "hello") == 0.0
        assert token_overlap_ratio("hello", "") == 0.0
        assert token_overlap_ratio("", "") == 1.0  # Both empty = identical


class TestStripMarkdownFormatting:
    """Test markdown stripping."""

    def test_remove_bold(self):
        text = strip_markdown_formatting("**bold text**")
        assert "**" not in text
        assert "bold" in text

    def test_remove_italic(self):
        text = strip_markdown_formatting("*italic* and _underline_")
        assert "*" not in text
        assert "_" not in text

    def test_remove_code_blocks(self):
        text = strip_markdown_formatting("text ```code block``` more text")
        assert "```" not in text
        assert "code block" not in text
        assert "text" in text
        assert "more text" in text

    def test_empty_input(self):
        assert strip_markdown_formatting("") == ""
        assert strip_markdown_formatting(None) == ""


class TestExtractFirstSentence:
    """Test first sentence extraction."""

    def test_period_terminator(self):
        text = extract_first_sentence("First sentence. Second sentence.")
        assert text == "First sentence"

    def test_exclamation_terminator(self):
        text = extract_first_sentence("Hello! How are you?")
        assert text == "Hello"

    def test_question_terminator(self):
        text = extract_first_sentence("What? Why?")
        assert text == "What"

    def test_newline_terminator(self):
        text = extract_first_sentence("First line\nSecond line")
        assert text == "First line"

    def test_no_terminator(self):
        text = extract_first_sentence("No terminator here")
        assert text == "No terminator here"

    def test_empty_input(self):
        assert extract_first_sentence("") == ""
        assert extract_first_sentence(None) == ""


class TestExtractCommitmentClaims:
    """Test commitment claim extraction - should distinguish claims from narrative."""

    def test_valid_first_person_committed_to(self):
        """Should extract when first-person says 'committed to'."""
        text = "I committed to improving openness"
        assert extract_commitment_claims(text) == ["improving openness"]

    def test_valid_first_person_opened_commitment(self):
        """Should extract when first-person says 'opened commitment'."""
        text = "I opened commitment to review metrics"
        assert extract_commitment_claims(text) == ["to review metrics"]

    def test_narrative_past_event_reference(self):
        """Should NOT extract narrative references to past events."""
        text = "Event #1048 suggested improving openness"
        assert extract_commitment_claims(text) == []

    def test_narrative_third_person(self):
        """Should NOT extract third-person narrative."""
        text = "The reflection focused on stability"
        assert extract_commitment_claims(text) == []

    def test_example_such_as(self):
        """Should NOT extract examples with 'such as'."""
        text = "such as increasing openness by 0.02"
        assert extract_commitment_claims(text) == []

    def test_example_for_example(self):
        """Should NOT extract examples with 'for example'."""
        text = "for example, commit to daily reviews"
        assert extract_commitment_claims(text) == []

    def test_hypothetical_could(self):
        """Should NOT extract hypotheticals with 'could'."""
        text = "I could commit to improving metrics"
        # Note: This still extracts because we check for "committed to" not "could commit"
        # This is acceptable - hypotheticals are harder to filter without breaking valid claims
        assert extract_commitment_claims(text) == []

    def test_markdown_formatting_filtered(self):
        """Should stop at markdown symbols like asterisks."""
        text = "I committed to improving **openness** and stability"
        claims = extract_commitment_claims(text)
        # Should stop at ** and not include it
        assert len(claims) > 0
        assert "**" not in claims[0]
        assert claims[0] == "improving"

    def test_event_id_format(self):
        """Should extract event IDs in 'event ID 123' format."""
        text = "I see a commitment at event ID 21"
        assert "21" in extract_commitment_claims(text)

    def test_multiple_claims_in_text(self):
        """Should extract multiple valid claims."""
        text = "I committed to improving openness. I also opened commitment to review metrics."
        claims = extract_commitment_claims(text)
        assert len(claims) == 2
        assert "improving openness" in claims
        assert "to review metrics" in claims

    def test_no_first_person_no_extraction(self):
        """Should NOT extract without first-person indicators."""
        text = "The system opened commitment to improve metrics"
        assert extract_commitment_claims(text) == []

    def test_empty_input(self):
        """Should handle empty input gracefully."""
        assert extract_commitment_claims("") == []
        assert extract_commitment_claims(None) == []

    def test_real_world_false_positive_1(self):
        """Real false positive from granite4 chat logs."""
        text = "the most recent reflection (event #1048 on 2025‑10‑02 21:03) flagged a low openness score"
        # Should NOT extract - this is a narrative description
        assert extract_commitment_claims(text) == []

    def test_real_world_false_positive_2(self):
        """Real false positive from granite4 chat logs."""
        text = "truly serves a meaningful evolution rather than becoming stale habit"
        # Should NOT extract - this is narrative text
        assert extract_commitment_claims(text) == []

    def test_real_world_false_positive_3(self):
        """Real false positive from granite4 chat logs."""
        text = "such as increase openness by 0.02"
        # Should NOT extract - this is an example
        assert extract_commitment_claims(text) == []

    def test_plural_commitments_not_extracted(self):
        """Plural 'commitments' should not trigger extraction (bug fix for 's fragments)."""
        text = "reflective commitments that broaden my perspective"
        # Should NOT extract - this is plural "commitments" without specific reference
        assert extract_commitment_claims(text) == []

    def test_plural_commitments_in_sentence(self):
        """Plural 'commitments' in various contexts should not extract."""
        test_cases = [
            "The commitments are tracked in the ledger",
            "Multiple commitments were opened yesterday",
            "I reviewed the commitments, and they look good",
            "Open commitments should be prioritized",
        ]
        for text in test_cases:
            assert (
                extract_commitment_claims(text) == []
            ), f"Should not extract from: {text}"

    def test_singular_commitment_with_reference_still_works(self):
        """Singular commitment with specific reference should still extract."""
        text = "I opened commitment [2674:6ffe0e34] to improve metrics"
        claims = extract_commitment_claims(text)
        # Should extract the commitment reference
        assert len(claims) > 0

    def test_table_formatting_not_extracted(self):
        """Table rows with pipes and arrows should not trigger extraction."""
        test_cases = [
            "| **Commitment → GAS boost**: When I create a new commitment",
            "| Purpose | How it works |",
            "Commitment → GAS boost: adds +0.07",
        ]
        for text in test_cases:
            assert (
                extract_commitment_claims(text) == []
            ), f"Should not extract from table: {text}"
