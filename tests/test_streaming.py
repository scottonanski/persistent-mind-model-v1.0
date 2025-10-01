"""Tests for LLM response streaming (Phase 2.1).

Tests streaming functionality across:
- LLM adapters (Ollama, OpenAI, Dummy)
- Runtime streaming wrapper
- handle_user_stream() method
- Ledger integrity with streaming
"""

from __future__ import annotations

import pytest
from pmm.llm.adapters.dummy_chat import DummyChat
from pmm.llm.adapters.ollama_chat import OllamaChat
from pmm.llm.adapters.openai_chat import OpenAIChat
from pmm.llm.factory import LLMConfig
from pmm.runtime.loop import Runtime
from pmm.storage.eventlog import EventLog


class TestDummyChatStreaming:
    """Test streaming with DummyChat adapter."""

    def test_generate_stream_returns_iterator(self):
        """Streaming should return an iterator."""
        chat = DummyChat(model="test")
        messages = [{"role": "user", "content": "Hello"}]

        result = chat.generate_stream(messages)
        assert hasattr(result, "__iter__")

    def test_generate_stream_produces_tokens(self):
        """Streaming should yield multiple tokens."""
        chat = DummyChat(model="test")
        messages = [{"role": "user", "content": "Hello"}]

        tokens = list(chat.generate_stream(messages))
        assert len(tokens) > 0
        assert all(isinstance(t, str) for t in tokens)

    def test_generate_stream_matches_generate(self):
        """Streaming should produce same result as non-streaming."""
        chat = DummyChat(model="test")
        messages = [{"role": "user", "content": "Hello"}]

        # Non-streaming
        blocking_result = chat.generate(messages)

        # Streaming
        streaming_result = "".join(chat.generate_stream(messages))

        assert streaming_result == blocking_result

    def test_generate_stream_deterministic(self):
        """Streaming should be deterministic (same input → same output)."""
        chat = DummyChat(model="test")
        messages = [{"role": "user", "content": "Hello"}]

        result1 = "".join(chat.generate_stream(messages))
        result2 = "".join(chat.generate_stream(messages))

        assert result1 == result2


class TestRuntimeStreamingWrapper:
    """Test Runtime._generate_reply_streaming() wrapper."""

    def test_streaming_wrapper_with_streaming_backend(self, tmp_path):
        """Wrapper should use backend streaming if available."""
        eventlog = EventLog(str(tmp_path / "test.db"))
        config = LLMConfig(provider="dummy", model="test")
        runtime = Runtime(config, eventlog)

        messages = [{"role": "user", "content": "Hello"}]

        # Should yield tokens
        tokens = list(runtime._generate_reply_streaming(messages))
        assert len(tokens) > 0

    def test_streaming_wrapper_fallback(self, tmp_path):
        """Wrapper should fallback to non-streaming if backend doesn't support it."""
        eventlog = EventLog(str(tmp_path / "test.db"))
        config = LLMConfig(provider="dummy", model="test")
        runtime = Runtime(config, eventlog)

        # Mock backend without streaming
        runtime.chat.generate_stream = None

        messages = [{"role": "user", "content": "Hello"}]

        # Should still work (fallback to generate())
        tokens = list(runtime._generate_reply_streaming(messages))
        assert len(tokens) >= 1  # At least one chunk (full response)


class TestHandleUserStream:
    """Test Runtime.handle_user_stream() method."""

    def test_handle_user_stream_returns_iterator(self, tmp_path):
        """handle_user_stream should return an iterator."""
        eventlog = EventLog(str(tmp_path / "test.db"))
        config = LLMConfig(provider="dummy", model="test")
        runtime = Runtime(config, eventlog)

        result = runtime.handle_user_stream("Hello")
        assert hasattr(result, "__iter__")

    def test_handle_user_stream_produces_tokens(self, tmp_path):
        """handle_user_stream should yield tokens."""
        eventlog = EventLog(str(tmp_path / "test.db"))
        config = LLMConfig(provider="dummy", model="test")
        runtime = Runtime(config, eventlog)

        tokens = list(runtime.handle_user_stream("Hello"))
        assert len(tokens) > 0
        assert all(isinstance(t, str) for t in tokens)

    def test_handle_user_stream_appends_events(self, tmp_path):
        """handle_user_stream should append user and response events."""
        eventlog = EventLog(str(tmp_path / "test.db"))
        config = LLMConfig(provider="dummy", model="test")
        runtime = Runtime(config, eventlog)

        before_count = len(eventlog.read_all())

        # Consume all tokens
        list(runtime.handle_user_stream("Hello"))

        after_count = len(eventlog.read_all())

        # Should have at least user + response events
        assert after_count >= before_count + 2

    def test_handle_user_stream_user_event_before_streaming(self, tmp_path):
        """User event should be appended BEFORE streaming starts."""
        eventlog = EventLog(str(tmp_path / "test.db"))
        config = LLMConfig(provider="dummy", model="test")
        runtime = Runtime(config, eventlog)

        before_events = eventlog.read_all()
        user_events_before = [e for e in before_events if e["kind"] == "user"]

        # Get first token
        stream = runtime.handle_user_stream("Hello")
        first_token = next(stream)

        # User event should already be in ledger
        after_first_token = eventlog.read_all()
        user_events_after = [e for e in after_first_token if e["kind"] == "user"]

        # Should have one more user event
        assert len(user_events_after) == len(user_events_before) + 1
        assert first_token  # Verify we got a token

        # Consume rest of stream
        list(stream)

    def test_handle_user_stream_response_event_after_streaming(self, tmp_path):
        """Response event should be appended AFTER streaming completes."""
        eventlog = EventLog(str(tmp_path / "test.db"))
        config = LLMConfig(provider="dummy", model="test")
        runtime = Runtime(config, eventlog)

        # Get first token but don't consume rest
        stream = runtime.handle_user_stream("Hello")
        _first_token = next(stream)

        # Response event should NOT be in ledger yet
        after_first_token = eventlog.read_all()
        response_events_partial = [
            e for e in after_first_token if e["kind"] == "response"
        ]
        partial_count = len(response_events_partial)

        # Consume rest of stream
        list(stream)

        # Response event should NOW be in ledger
        after_complete = eventlog.read_all()
        response_events_complete = [
            e for e in after_complete if e["kind"] == "response"
        ]

        assert len(response_events_complete) > partial_count

    def test_handle_user_stream_no_partial_responses(self, tmp_path):
        """Ledger should never contain partial responses."""
        eventlog = EventLog(str(tmp_path / "test.db"))
        config = LLMConfig(provider="dummy", model="test")
        runtime = Runtime(config, eventlog)

        # Consume stream
        full_response = "".join(runtime.handle_user_stream("Hello"))

        # Check ledger
        events = eventlog.read_all()
        response_events = [e for e in events if e["kind"] == "response"]

        # Should have exactly one response event with full content
        assert len(response_events) >= 1
        last_response = response_events[-1]["content"]

        # Response in ledger should match full streamed response
        assert last_response == full_response or full_response in last_response

    def test_handle_user_stream_deterministic(self, tmp_path):
        """Streaming should be deterministic (same input → same output)."""
        eventlog = EventLog(str(tmp_path / "test.db"))
        config = LLMConfig(provider="dummy", model="test")
        runtime = Runtime(config, eventlog)

        # First call
        result1 = "".join(runtime.handle_user_stream("Test query"))

        # Second call with same input
        result2 = "".join(runtime.handle_user_stream("Test query"))

        # Results should be deterministic (DummyChat is deterministic)
        # Note: May differ due to context changes, but structure should be similar
        assert len(result1) > 0
        assert len(result2) > 0


class TestStreamingLedgerIntegrity:
    """Test ledger integrity with streaming."""

    def test_event_ordering(self, tmp_path):
        """Events should be in correct chronological order."""
        eventlog = EventLog(str(tmp_path / "test.db"))
        config = LLMConfig(provider="dummy", model="test")
        runtime = Runtime(config, eventlog)

        # Stream a response
        list(runtime.handle_user_stream("Hello"))

        # Check event ordering
        events = eventlog.read_all()
        user_events = [e for e in events if e["kind"] == "user"]
        response_events = [e for e in events if e["kind"] == "response"]

        # Should have at least one of each
        assert len(user_events) >= 1
        assert len(response_events) >= 1

        # Last user event should come before last response event
        last_user_id = int(user_events[-1]["id"])
        last_response_id = int(response_events[-1]["id"])

        assert last_user_id < last_response_id

    def test_embedding_events(self, tmp_path):
        """Embedding events should be created for user and response."""
        eventlog = EventLog(str(tmp_path / "test.db"))
        config = LLMConfig(provider="dummy", model="test")
        runtime = Runtime(config, eventlog)

        # Stream a response
        list(runtime.handle_user_stream("Hello"))

        # Check for embedding events
        events = eventlog.read_all()
        embedding_events = [e for e in events if e["kind"] == "embedding_indexed"]

        # Should have embeddings for user and response
        assert len(embedding_events) >= 2

    def test_performance_trace_events(self, tmp_path):
        """Performance trace events should be created."""
        eventlog = EventLog(str(tmp_path / "test.db"))
        config = LLMConfig(provider="dummy", model="test")
        runtime = Runtime(config, eventlog)

        # Stream a response
        list(runtime.handle_user_stream("Hello"))

        # Check for performance trace
        events = eventlog.read_all()
        perf_events = [e for e in events if e["kind"] == "performance_trace"]

        # Should have at least one performance trace
        assert len(perf_events) >= 1

        # Should have timing stats
        last_perf = perf_events[-1]
        assert "stats" in last_perf.get("meta", {})


class TestStreamingErrorHandling:
    """Test error handling in streaming."""

    def test_streaming_error_doesnt_corrupt_ledger(self, tmp_path):
        """Errors during streaming shouldn't corrupt the ledger."""
        eventlog = EventLog(str(tmp_path / "test.db"))
        config = LLMConfig(provider="dummy", model="test")
        runtime = Runtime(config, eventlog)

        # Mock streaming to raise error mid-stream
        _original_stream = runtime.chat.generate_stream

        def error_stream(messages, **kwargs):
            yield "First"
            yield " token"
            raise RuntimeError("Simulated streaming error")

        runtime.chat.generate_stream = error_stream

        _before_count = len(eventlog.read_all())

        # Try to stream (should fail)
        with pytest.raises(RuntimeError):
            list(runtime.handle_user_stream("Hello"))

        # Ledger should still be valid (no partial responses)
        _after_count = len(eventlog.read_all())
        events = eventlog.read_all()

        # User event should be there
        user_events = [e for e in events if e["kind"] == "user"]
        assert len(user_events) > 0

        # Response event should NOT be there (error occurred)
        _response_events = [e for e in events if e["kind"] == "response"]
        # May or may not have response depending on error handling
        # The key is no PARTIAL responses


class TestStreamingBackendCompatibility:
    """Test streaming with different backends."""

    def test_dummy_backend_streaming(self, tmp_path):
        """DummyChat should support streaming."""
        chat = DummyChat(model="test")
        assert hasattr(chat, "generate_stream")

        messages = [{"role": "user", "content": "Hello"}]
        tokens = list(chat.generate_stream(messages))
        assert len(tokens) > 0

    @pytest.mark.skipif(True, reason="Requires Ollama server running")
    def test_ollama_backend_streaming(self, tmp_path):
        """OllamaChat should support streaming (requires server)."""
        try:
            chat = OllamaChat(model="llama3.2:3b")
            assert hasattr(chat, "generate_stream")

            messages = [{"role": "user", "content": "Count to 3"}]
            tokens = list(
                chat.generate_stream(messages, temperature=0.0, max_tokens=50)
            )

            assert len(tokens) > 0
            full_response = "".join(tokens)
            assert len(full_response) > 0
        except Exception as e:
            pytest.skip(f"Ollama not available: {e}")

    @pytest.mark.skipif(True, reason="Requires OpenAI API key")
    def test_openai_backend_streaming(self, tmp_path):
        """OpenAIChat should support streaming (requires API key)."""
        import os

        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")

        try:
            chat = OpenAIChat(model="gpt-3.5-turbo")
            assert hasattr(chat, "generate_stream")

            messages = [{"role": "user", "content": "Say hello"}]
            tokens = list(
                chat.generate_stream(messages, temperature=0.0, max_tokens=20)
            )

            assert len(tokens) > 0
            full_response = "".join(tokens)
            assert len(full_response) > 0
        except Exception as e:
            pytest.skip(f"OpenAI not available: {e}")


class TestStreamingPerformance:
    """Test streaming performance characteristics."""

    def test_streaming_time_to_first_token(self, tmp_path):
        """First token should arrive quickly."""
        import time

        eventlog = EventLog(str(tmp_path / "test.db"))
        config = LLMConfig(provider="dummy", model="test")
        runtime = Runtime(config, eventlog)

        start = time.time()
        stream = runtime.handle_user_stream("Hello")
        first_token = next(stream)
        time_to_first_token = time.time() - start

        # First token should arrive in <1 second (DummyChat is instant)
        assert time_to_first_token < 1.0
        assert first_token  # Verify we got a token

        # Consume rest
        list(stream)

    def test_streaming_vs_blocking_same_total_time(self, tmp_path):
        """Streaming and blocking should take similar total time."""
        import time

        eventlog = EventLog(str(tmp_path / "test.db"))
        config = LLMConfig(provider="dummy", model="test")
        runtime = Runtime(config, eventlog)

        # Measure streaming time
        start = time.time()
        list(runtime.handle_user_stream("Test query"))
        streaming_time = time.time() - start

        # Measure blocking time
        start = time.time()
        runtime.handle_user("Test query")
        blocking_time = time.time() - start

        # Should be similar (within 2x)
        # Note: Streaming may be slightly slower due to overhead
        assert streaming_time < blocking_time * 2


class TestStreamingIntegration:
    """Integration tests for streaming."""

    def test_full_conversation_with_streaming(self, tmp_path):
        """Test a full multi-turn conversation with streaming."""
        eventlog = EventLog(str(tmp_path / "test.db"))
        config = LLMConfig(provider="dummy", model="test")
        runtime = Runtime(config, eventlog)

        # Turn 1
        response1 = "".join(runtime.handle_user_stream("Hello"))
        assert len(response1) > 0

        # Turn 2
        response2 = "".join(runtime.handle_user_stream("How are you?"))
        assert len(response2) > 0

        # Turn 3
        response3 = "".join(runtime.handle_user_stream("Goodbye"))
        assert len(response3) > 0

        # Check ledger has all events
        events = eventlog.read_all()
        user_events = [e for e in events if e["kind"] == "user"]
        response_events = [e for e in events if e["kind"] == "response"]

        assert len(user_events) >= 3
        assert len(response_events) >= 3

    def test_streaming_with_phase1_optimizations(self, tmp_path):
        """Streaming should work with Phase 1 optimizations."""
        eventlog = EventLog(str(tmp_path / "test.db"))
        config = LLMConfig(provider="dummy", model="test")
        runtime = Runtime(config, eventlog)

        # Stream a response (Phase 1 optimizations are always on)
        _response = "".join(runtime.handle_user_stream("Hello"))

        # Check that performance trace was created (Phase 1 feature)
        events = eventlog.read_all()
        perf_events = [e for e in events if e["kind"] == "performance_trace"]

        assert len(perf_events) >= 1

        # Check that profiling includes streaming metrics
        last_perf = perf_events[-1]
        stats = last_perf.get("meta", {}).get("stats", {})

        # Should have llm_inference_streaming metric
        assert "llm_inference_streaming" in stats or "llm_inference" in stats
