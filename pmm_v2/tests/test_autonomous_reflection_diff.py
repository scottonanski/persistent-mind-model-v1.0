import pytest
from unittest.mock import Mock

from pmm_v2.runtime.reflection_synthesizer import synthesize_reflection


def test_autonomous_reflection_diff():
    """Test that user-turn and autonomous reflections produce different content."""
    mock_eventlog = Mock()
    events = [
        {"kind": "user_message", "content": "some intent"},
        {"kind": "assistant_message", "content": "some outcome"},
        {"kind": "metrics_turn", "content": "provider:dummy,model:none,in_tokens:1,out_tokens:1,lat_ms:0"},
        {"kind": "commitment_open", "meta": {"cid": "c1"}, "content": "commit 1"},
        {"kind": "commitment_open", "meta": {"cid": "c2"}, "content": "commit 2"},
    ]
    mock_eventlog.read_all.return_value = events
    mock_eventlog.append.return_value = 123

    # Test user-turn reflection
    synthesize_reflection(mock_eventlog, source="user_turn")
    call_args = mock_eventlog.append.call_args
    assert call_args[1]["kind"] == "reflection"
    content = call_args[1]["content"]
    assert content.startswith("{intent:'some intent'")

    # Reset mock
    mock_eventlog.append.reset_mock()

    # Test autonomous reflection
    synthesize_reflection(mock_eventlog, source="autonomy_kernel")
    call_args = mock_eventlog.append.call_args
    assert call_args[1]["kind"] == "reflection"
    content = call_args[1]["content"]
    assert content.startswith("{commitments_reviewed:2,")
