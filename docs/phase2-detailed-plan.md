# Phase 2: Architectural Improvements - Detailed Plan

## Executive Summary

**Goal**: Reduce perceived latency from 3000ms to 200ms through LLM streaming  
**Timeline**: 1-2 weeks  
**Expected Impact**: 65% total improvement (4317ms → 1500ms actual, 200ms perceived)  
**Risk Level**: Medium (async refactoring required)

---

## Component 2.1: LLM Response Streaming (Priority 1)

### Overview

Stream LLM tokens as they're generated instead of waiting for the complete response. This provides a **15x improvement in perceived latency** (3000ms → 200ms).

### Current Flow

```python
def handle_user(self, user_text: str) -> str:
    # Build context
    context = build_context_from_ledger(...)
    
    # Wait for ENTIRE response (3000ms of blocking)
    reply = self._generate_reply(messages)  # User sees nothing
    
    # Post-process
    self.eventlog.append(kind="response", content=reply)
    
    return reply  # Finally shown to user
```

**Problem**: User waits 3000ms staring at blank screen.

### Proposed Flow

```python
def handle_user_streaming(self, user_text: str) -> Iterator[str]:
    # Build context (cached from Phase 1)
    context = build_context_from_ledger(...)
    
    # Stream tokens as they arrive
    full_response = []
    for token in self._generate_reply_streaming(messages):
        yield token  # Show immediately!
        full_response.append(token)
    
    # Post-process complete response
    reply = "".join(full_response)
    self.eventlog.append(kind="response", content=reply)
```

**Benefit**: User sees first token in ~200ms, feels instant.

---

### Implementation Steps

#### Step 1: Add Streaming Support to LLM Backends

**File**: `pmm/llm/factory.py`

```python
class ChatAdapter:
    def generate_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> Iterator[str]:
        """Stream response tokens as they're generated.
        
        Yields:
            Individual tokens or token chunks
        """
        raise NotImplementedError("Subclass must implement generate_stream")
```

**Backends to Update:**
- `OllamaChat` - Already supports streaming via `/api/chat` endpoint
- `OpenAIChat` - Supports streaming via `stream=True`
- `AnthropicChat` - Supports streaming via `stream=True`
- `LlamaCppChat` - Supports streaming natively

#### Step 2: Create Streaming Wrapper in Runtime

**File**: `pmm/runtime/loop.py`

```python
def _generate_reply_streaming(
    self,
    messages: list[dict],
    *,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> Iterator[str]:
    """Generate reply with token streaming.
    
    Yields tokens as they arrive from the LLM.
    """
    try:
        for token in self.chat.generate_stream(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield token
    except NotImplementedError:
        # Fallback to non-streaming for backends that don't support it
        reply = self._generate_reply(messages, temperature, max_tokens)
        yield reply
```

#### Step 3: Refactor handle_user() to Support Streaming

**File**: `pmm/runtime/loop.py`

```python
def handle_user(self, user_text: str, stream: bool = False):
    """Handle user input with optional streaming.
    
    Args:
        user_text: User's message
        stream: If True, returns iterator. If False, returns string.
        
    Returns:
        Iterator[str] if stream=True, str otherwise
    """
    if stream:
        return self._handle_user_streaming(user_text)
    else:
        return self._handle_user_blocking(user_text)

def _handle_user_streaming(self, user_text: str) -> Iterator[str]:
    """Streaming version of handle_user."""
    # ... (implementation below)

def _handle_user_blocking(self, user_text: str) -> str:
    """Non-streaming version (current behavior)."""
    # Collect all tokens from streaming version
    return "".join(self._handle_user_streaming(user_text))
```

#### Step 4: Update CLI to Support Streaming

**File**: `pmm/cli/chat.py`

```python
def chat_loop(runtime):
    while True:
        user_input = input("You: ")
        
        print("PMM: ", end="", flush=True)
        for token in runtime.handle_user(user_input, stream=True):
            print(token, end="", flush=True)
        print()  # Newline after complete response
```

#### Step 5: Update Companion API to Support Streaming

**File**: `pmm/api/companion.py`

```python
from fastapi.responses import StreamingResponse

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Stream chat response as Server-Sent Events."""
    
    def generate():
        for token in runtime.handle_user(request.message, stream=True):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
    )
```

---

### Detailed Implementation: _handle_user_streaming()

```python
def _handle_user_streaming(self, user_text: str) -> Iterator[str]:
    """Stream response tokens while maintaining ledger integrity."""
    
    # Phase 1 optimizations (already in place)
    from pmm.runtime.profiler import get_global_profiler
    from pmm.runtime.request_cache import CachedEventLog
    
    profiler = get_global_profiler()
    request_log = CachedEventLog(self.eventlog)
    
    # Build context (cached)
    with profiler.measure("snapshot_build"):
        snapshot = self._get_snapshot()
    
    with profiler.measure("context_build"):
        context_block = build_context_from_ledger(
            self.eventlog,
            n_reflections=3,
            snapshot=snapshot,
            memegraph=self.memegraph,
            max_commitment_chars=MAX_COMMITMENT_CHARS,
            max_reflection_chars=MAX_REFLECTION_CHARS,
        )
    
    # Append user event BEFORE streaming (must be in ledger)
    user_event_id = self.eventlog.append(
        kind="user",
        content=user_text,
        meta={"ts": time.time()},
    )
    
    # Build messages
    msgs = [
        {"role": "system", "content": context_block},
        {"role": "system", "content": build_system_msg("chat")},
        {"role": "user", "content": user_text},
    ]
    
    # Add state intents if detected
    intents = self._detect_state_intents(user_text)
    if intents:
        try:
            state_summary = self.describe_state()
            summary_text = self._format_state_summary(state_summary, intents)
            if summary_text:
                msgs.append({"role": "system", "content": summary_text})
        except Exception:
            logger.debug("State summary injection failed", exc_info=True)
    
    # Start reasoning trace
    if self.trace_buffer:
        self.trace_buffer.start_session(query=user_text[:200])
        self.trace_buffer.add_reasoning_step("Building context from ledger")
        self.trace_buffer.add_reasoning_step("Streaming LLM response")
    
    # Stream LLM response
    styled = self.bridge.format_messages(msgs, intent="chat")
    full_response = []
    
    with profiler.measure("llm_inference_streaming"):
        for token in self._generate_reply_streaming(
            styled,
            temperature=0.3,
            max_tokens=2048,
        ):
            full_response.append(token)
            yield token  # Stream to user immediately
    
    # Reconstruct complete response
    reply = "".join(full_response)
    
    # Post-processing (synchronous - must complete before next query)
    with profiler.measure("post_processing"):
        # Sanitize
        try:
            reply = self.bridge.sanitize(
                reply,
                family=self.bridge.model_family,
                adopted_name=build_identity(self.eventlog.read_all()).get("name"),
            )
        except Exception:
            pass
        
        # Apply trait adjustments
        try:
            applied_events = apply_llm_trait_adjustments(self.eventlog, reply)
            if applied_events:
                logger.info(f"Applied {len(applied_events)} LLM trait adjustments")
        except Exception as e:
            logger.warning(f"LLM trait adjustment failed: {e}")
        
        # Append response event
        response_event_id = self.eventlog.append(
            kind="response",
            content=reply,
            meta={"user_event_id": user_event_id},
        )
        
        # Index embeddings
        try:
            vec = _emb.compute_embedding(reply)
            if isinstance(vec, list) and vec:
                self.eventlog.append(
                    kind="embedding_indexed",
                    content="",
                    meta={"eid": int(response_event_id), "digest": _emb.digest_vector(vec)},
                )
        except Exception:
            pass
        
        # Extract commitments
        try:
            commitments = extract_commitments(reply, self.eventlog)
            # ... (existing commitment logic)
        except Exception:
            pass
        
        # Note user turn for reflection cooldown
        self.cooldown.note_user_turn()
    
    # Flush traces and profiling
    if self.trace_buffer:
        try:
            self.trace_buffer.add_reasoning_step("Response streamed and processed")
            self.trace_buffer.flush_to_eventlog(self.eventlog)
        except Exception:
            logger.exception("Failed to flush reasoning trace")
    
    try:
        profiler.export_to_trace_event(self.eventlog)
        cache_stats = request_log.get_cache_stats()
        logger.debug(
            f"Request cache: {cache_stats['hits']} hits, "
            f"{cache_stats['misses']} misses, "
            f"hit_rate={cache_stats['hit_rate']:.1%}"
        )
    except Exception:
        logger.debug("Failed to export performance profile", exc_info=True)
```

---

### Testing Strategy

#### Unit Tests

```python
# tests/test_streaming.py

def test_streaming_returns_iterator():
    runtime = Runtime(config, eventlog)
    result = runtime.handle_user("Hello", stream=True)
    assert hasattr(result, '__iter__')

def test_streaming_produces_tokens():
    runtime = Runtime(config, eventlog)
    tokens = list(runtime.handle_user("Hello", stream=True))
    assert len(tokens) > 0
    assert all(isinstance(t, str) for t in tokens)

def test_streaming_matches_blocking():
    runtime = Runtime(config, eventlog)
    
    # Streaming version
    streamed = "".join(runtime.handle_user("Hello", stream=True))
    
    # Blocking version
    blocked = runtime.handle_user("Hello", stream=False)
    
    # Should produce same result
    assert streamed == blocked

def test_streaming_appends_events():
    runtime = Runtime(config, eventlog)
    
    before_count = len(eventlog.read_all())
    list(runtime.handle_user("Hello", stream=True))
    after_count = len(eventlog.read_all())
    
    # Should append user + response events
    assert after_count >= before_count + 2
```

#### Integration Tests

```python
def test_streaming_with_ollama():
    """Test streaming with Ollama backend."""
    config = LLMConfig(provider="ollama", model="llama3.2:3b")
    runtime = Runtime(config, eventlog)
    
    tokens = []
    for token in runtime.handle_user("Count to 5", stream=True):
        tokens.append(token)
        # Verify tokens arrive incrementally
        assert len(token) < 100  # Individual tokens, not full response
    
    full_response = "".join(tokens)
    assert "1" in full_response
    assert "5" in full_response

def test_streaming_fallback():
    """Test fallback to blocking for non-streaming backends."""
    # Mock backend without streaming support
    runtime = Runtime(config, eventlog)
    runtime.chat.generate_stream = None  # Simulate no streaming
    
    # Should still work (fallback to blocking)
    result = list(runtime.handle_user("Hello", stream=True))
    assert len(result) == 1  # Single chunk (full response)
```

#### Performance Benchmarks

```python
def benchmark_streaming_latency():
    """Measure time to first token vs full response."""
    runtime = Runtime(config, eventlog)
    
    # Measure time to first token
    start = time.time()
    stream = runtime.handle_user("Write a story", stream=True)
    first_token = next(stream)
    time_to_first_token = time.time() - start
    
    # Consume rest
    list(stream)
    total_time = time.time() - start
    
    print(f"Time to first token: {time_to_first_token*1000:.0f}ms")
    print(f"Total time: {total_time*1000:.0f}ms")
    
    # First token should be much faster
    assert time_to_first_token < 500  # <500ms
    assert total_time > 2000  # >2s for full response
```

---

### Compatibility with Ledger → Mirror → Memegraph

#### ✅ Ledger Integrity

- User event appended **before** streaming starts
- Response event appended **after** streaming completes
- All events in correct order
- No partial responses in ledger

#### ✅ Mirror (Projections)

- Projections built from complete events only
- Streaming doesn't affect projection logic
- Identity, self-model, metrics unchanged

#### ✅ Memegraph

- Graph updated after complete response
- No partial data in graph
- Reasoning traces still work

#### ✅ Determinism

- Same input → same output (same tokens, same order)
- Streaming is just delivery mechanism
- Ledger replay produces identical results

---

### Rollout Plan

#### Phase 2.1.1: Backend Streaming Support (Days 1-2)

- [ ] Add `generate_stream()` to `ChatAdapter` interface
- [ ] Implement streaming for `OllamaChat`
- [ ] Implement streaming for `OpenAIChat`
- [ ] Implement streaming for `AnthropicChat`
- [ ] Add fallback for non-streaming backends
- [ ] Unit test each backend

#### Phase 2.1.2: Runtime Integration (Days 3-4)

- [ ] Create `_generate_reply_streaming()` wrapper
- [ ] Refactor `handle_user()` to support `stream` parameter
- [ ] Implement `_handle_user_streaming()`
- [ ] Ensure post-processing happens after streaming
- [ ] Integration tests

#### Phase 2.1.3: CLI & API Updates (Day 5)

- [ ] Update `pmm/cli/chat.py` to stream by default
- [ ] Add `/chat/stream` endpoint to Companion API
- [ ] Update Companion UI to use streaming
- [ ] End-to-end testing

#### Phase 2.1.4: Testing & Validation (Days 6-7)

- [ ] Performance benchmarks
- [ ] Verify ledger integrity
- [ ] Test with all LLM backends
- [ ] Stress testing (long responses, errors, interrupts)
- [ ] Documentation updates

---

### Risk Mitigation

#### Risk 1: Partial Response on Error

**Scenario**: LLM stream fails mid-response

**Mitigation**:
```python
try:
    for token in stream:
        yield token
        full_response.append(token)
except Exception as e:
    # Log error but don't append partial response
    logger.error(f"Streaming failed: {e}")
    # Append error event instead
    self.eventlog.append(
        kind="error",
        content=f"Streaming failed: {e}",
        meta={"partial_response": "".join(full_response)},
    )
    return
```

#### Risk 2: Post-Processing Fails

**Scenario**: Embedding/commitment extraction fails after streaming

**Mitigation**:
- Wrap each post-processing step in try/except
- Log failures but don't block
- Response already delivered to user
- Background tasks can retry

#### Risk 3: Backend Doesn't Support Streaming

**Scenario**: User has custom LLM backend without streaming

**Mitigation**:
```python
def _generate_reply_streaming(self, messages, **kwargs):
    if hasattr(self.chat, 'generate_stream'):
        for token in self.chat.generate_stream(messages, **kwargs):
            yield token
    else:
        # Fallback: yield entire response at once
        reply = self._generate_reply(messages, **kwargs)
        yield reply
```

---

### Success Criteria

- [ ] Time to first token < 500ms (target: 200ms)
- [ ] Total time unchanged (~3000ms)
- [ ] All events appended to ledger correctly
- [ ] No partial responses in ledger
- [ ] Streaming works with all supported LLM backends
- [ ] Fallback works for non-streaming backends
- [ ] CLI shows streaming output
- [ ] Companion UI shows streaming output
- [ ] All tests passing
- [ ] No performance regression

---

### Performance Expectations

| Metric | Before Phase 2 | After Phase 2 |
|--------|----------------|---------------|
| **Time to First Token** | 3000ms | **200ms** ⚡ |
| **Total Response Time** | 3000ms | 3000ms |
| **Perceived Latency** | 3000ms | **200ms** ⚡ |
| **User Experience** | "Slow" | **"Instant"** |

---

## Component 2.2: Incremental Snapshots (Priority 2)

### Overview

Update snapshots incrementally instead of rebuilding from scratch on every query.

### Current Behavior

```python
def _get_snapshot(self):
    # Always rebuilds EVERYTHING
    events = self.eventlog.read_all()  # 1000+ events
    identity = build_identity(events)  # Process all
    self_model = build_self_model(events)  # Process all
    # ...
```

**Problem**: Wastes time re-processing events we've already seen.

### Proposed Behavior

```python
def _get_snapshot(self):
    current_id = self._get_last_event_id()
    
    # Cache still valid?
    if self._snapshot_cache and current_id == self._last_snapshot_id:
        return self._snapshot_cache  # No rebuild!
    
    # Only process NEW events
    if self._snapshot_cache:
        new_events = self.eventlog.read_since(self._last_snapshot_id)
        self._snapshot_cache.update_incremental(new_events)
    else:
        # First time: full rebuild
        events = self.eventlog.read_all()
        self._snapshot_cache = LedgerSnapshot.from_events(events)
    
    self._last_snapshot_id = current_id
    return self._snapshot_cache
```

**Benefit**: 100-200ms savings on subsequent queries in same session.

### Implementation Complexity

**Medium** - Need to ensure incremental updates are correct for:
- Identity changes (name adoption)
- Trait updates
- Commitment state changes
- Stage transitions
- Policy updates

### Timeline

- Days 1-2: Design incremental update logic
- Day 3: Implement `LedgerSnapshot.update_incremental()`
- Day 4: Update `_get_snapshot()` to use incremental logic
- Day 5: Testing and validation

---

## Component 2.3: Background Processing (Priority 3 - Optional)

### Overview

Move non-critical post-processing off the critical path.

### What Can Go to Background

- ✅ Embedding indexing (not needed for next query)
- ✅ Scene compaction (cleanup task)
- ✅ Audit reports (introspection)
- ✅ Semantic growth reports (analysis)

### What Must Stay Synchronous

- ❌ User event append (must be in ledger)
- ❌ Response event append (must be in ledger)
- ❌ Commitment extraction (affects next query context)
- ❌ Trait adjustments (affects next query context)
- ❌ Reflection triggers (affects autonomy loop)

### Implementation Complexity

**HIGH** - Requires:
- Thread-safe task queue
- Proper ordering guarantees
- Error handling and retries
- Graceful shutdown
- Testing for race conditions

### Timeline

- Days 1-2: Design background processor
- Days 3-4: Implement task queue with ordering
- Day 5: Integrate with `handle_user()`
- Days 6-7: Extensive testing for race conditions

### Recommendation

**Defer to Phase 3** - The complexity and risk aren't worth the 200-400ms savings. Focus on streaming first.

---

## Phase 2 Timeline Summary

### Week 1: LLM Streaming (2.1)
- **Days 1-2**: Backend streaming support
- **Days 3-4**: Runtime integration
- **Day 5**: CLI & API updates
- **Days 6-7**: Testing & validation

### Week 2: Incremental Snapshots (2.2) - Optional
- **Days 1-3**: Implementation
- **Days 4-5**: Testing

**Total**: 1-2 weeks depending on scope

---

## Success Metrics

### Must Have (2.1 - Streaming)
- [ ] Time to first token < 500ms
- [ ] Streaming works with all backends
- [ ] Ledger integrity maintained
- [ ] All tests passing

### Nice to Have (2.2 - Incremental Snapshots)
- [ ] 100-200ms faster on subsequent queries
- [ ] No correctness regressions
- [ ] Memory usage acceptable

### Skip for Now (2.3 - Background Processing)
- Defer to Phase 3 or later

---

## Next Steps

Ready to implement **Phase 2.1: LLM Streaming**?

I'll start with:
1. Adding `generate_stream()` to ChatAdapter interface
2. Implementing streaming for Ollama (most common backend)
3. Creating `_handle_user_streaming()` in Runtime
4. Updating CLI to stream by default

Let's make PMM feel instant! 🚀
