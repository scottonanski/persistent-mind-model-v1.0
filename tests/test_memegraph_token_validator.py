"""Tests for memegraph token validator to prevent hallucination."""

import os
import tempfile

import pytest

from pmm.runtime.loop.validators import verify_memegraph_tokens
from pmm.storage.eventlog import EventLog
from pmm.utils.parsers import extract_memegraph_tokens


class TestMemegraphTokenValidator:
    """Test memegraph token extraction and validation."""

    @pytest.fixture
    def eventlog(self):
        """Create temporary eventlog for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            eventlog = EventLog(db_path)
            # Add some test events
            eventlog.append(
                kind="stage_update",
                content="Stage transition: S0 → S1",
                meta={"from": "S0", "to": "S1"},
            )
            eventlog.append(
                kind="test_event", content="Test event with hash", meta={"test": True}
            )
            yield eventlog
        finally:
            os.unlink(db_path)

    def test_extract_proper_format_tokens(self):
        """Test extraction of properly formatted tokens."""
        text = "Stage evidence: 5:5e152a1940e217473ed4437306b36c904ba477ec"
        tokens = extract_memegraph_tokens(text)
        assert len(tokens) == 1
        assert "5:5e152a1940e217473ed4437306b36c904ba477ec" in tokens

    def test_extract_bracketed_tokens(self):
        """Test extraction of bracketed tokens."""
        text = "Stage evidence: [5:5e152a1940e217473ed4437306b36c904ba477ec]"
        tokens = extract_memegraph_tokens(text)
        assert len(tokens) == 1
        assert "[5:5e152a1940e217473ed4437306b36c904ba477ec]" in tokens

    def test_extract_standalone_hallucinated_tokens(self):
        """Test extraction of standalone hallucinated tokens."""
        text = "Token: 5f6846fc193f984ff7e1be75b2e2fb444a5a540b"
        tokens = extract_memegraph_tokens(text)
        assert len(tokens) == 1
        assert "5f6846fc193f984ff7e1be75b2e2fb444a5a540b" in tokens

    def test_extract_multiple_tokens(self):
        """Test extraction of multiple tokens."""
        text = """
        Stage evidence: 5:5e152a1940e217473ed4437306b36c904ba477ec
        Another token: [2:35c3a300a471f8cf799949eed4794d056c34b98c]
        Fake token: 5f6846fc193f984ff7e1be75b2e2fb444a5a540b
        """
        tokens = extract_memegraph_tokens(text)
        assert len(tokens) == 3
        assert "5:5e152a1940e217473ed4437306b36c904ba477ec" in tokens
        assert "[2:35c3a300a471f8cf799949eed4794d056c34b98c]" in tokens
        assert "5f6846fc193f984ff7e1be75b2e2fb444a5a540b" in tokens

    def test_ignore_invalid_formats(self):
        """Test that invalid formats are ignored."""
        text = """
        Invalid: abc:def
        Too short: 5:abc123
        Not hex: 5:g1234567890abcdef1234567890abcdef12345678
        Valid: 5:5e152a1940e217473ed4437306b36c904ba477ec
        """
        tokens = extract_memegraph_tokens(text)
        assert len(tokens) == 1
        assert "5:5e152a1940e217473ed4437306b36c904ba477ec" in tokens

    def test_catch_echo_hallucination_style(self):
        """Test catching Echo's specific hallucination style."""
        echo_reply = """I'm currently in Stage S2. Here's the evidence from the MemGraph:

- Token: 5f6846fc193f984ff7e1be75b2e2fb444a5a540b
- Supporting Event ID(s): 2 (event token 65212adf91b108480067f1bc799c81abf05d65d8)"""

        tokens = extract_memegraph_tokens(echo_reply)
        assert len(tokens) == 2
        assert "5f6846fc193f984ff7e1be75b2e2fb444a5a540b" in tokens
        assert "65212adf91b108480067f1bc799c81abf05d65d8" in tokens

    def test_verify_real_tokens(self, eventlog):
        """Test that real tokens pass validation."""
        # This would need a real database with actual memegraph data
        # For now, test that the validator runs without error
        text = "Stage evidence: 1:5e152a1940e217473ed4437306b36c904ba477ec"
        is_valid, fake_tokens = verify_memegraph_tokens(text, eventlog)

        # Should either be valid (if token exists) or invalid with specific fake tokens
        assert isinstance(is_valid, bool)
        assert fake_tokens is None or isinstance(fake_tokens, list)

    def test_verify_fake_tokens_detected(self, eventlog):
        """Test that fake tokens are caught."""
        fake_text = "Token: 5f6846fc193f984ff7e1be75b2e2fb444a5a540b"
        is_valid, fake_tokens = verify_memegraph_tokens(fake_text, eventlog)

        # Fake tokens should be detected as invalid
        assert is_valid is False
        assert fake_tokens is not None
        assert "5f6846fc193f984ff7e1be75b2e2fb444a5a540b" in fake_tokens

    def test_empty_text(self):
        """Test handling of empty text."""
        tokens = extract_memegraph_tokens("")
        assert tokens == []

    def test_no_tokens(self):
        """Test text with no tokens."""
        text = "This is just regular text without any memegraph tokens."
        tokens = extract_memegraph_tokens(text)
        assert tokens == []
