"""Test token citation integrity and apostrophe handling.

This test validates the fix for the truncation-induced hallucination bug
where Echo would fabricate token completions when receiving truncated digests.
"""

import os
import tempfile

from pmm.runtime.context_builder import build_context_from_ledger
from pmm.runtime.memegraph import MemeGraphProjection
from pmm.storage.eventlog import EventLog


class TestTokenCitation:
    """Test token citation accuracy and special character handling."""

    def test_apostrophe_content_full_tokens(self):
        """Test that content with apostrophes receives full digest tokens."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Initialize components
            eventlog = EventLog(db_path)
            memegraph = MemeGraphProjection(eventlog)

            # Add events with apostrophes (previously caused hallucinations)
            test_events = [
                (
                    "commitment_open",
                    "When I say something, it's not just a string of words; it's a reflection",
                ),
                (
                    "commitment_open",
                    "I'm focused on self-awareness and personal growth",
                ),
                (
                    "commitment_open",
                    "The policy's effectiveness depends on user feedback",
                ),
                (
                    "reflection",
                    "I can't believe how much I've learned through this process",
                ),
                ("reflection", "Don't underestimate the power of persistent memory"),
            ]

            event_ids = []
            for kind, content in test_events:
                # Use proper digest-length CID instead of short string
                cid = f"test_digest_{len(event_ids):028x}"  # 32-char hex-like string
                eid = eventlog.append(kind=kind, content=content, meta={"cid": cid})
                event_ids.append((eid, cid))

            # Build context with reflections enabled
            context = build_context_from_ledger(
                eventlog,
                memegraph=memegraph,
                include_reflections=True,
                include_commitments=True,
                n_reflections=5,
            )

            # Verify all tokens are full digests (not truncated)
            for eid, expected_cid in event_ids:
                # Find the line with this event ID
                lines = context.split("\n")
                for line in lines:
                    if f"[{eid}:" in line:
                        # Extract token part
                        token_part = (
                            line.split(f"[{eid}:")[1].split("]")[0]
                            if "]" in line.split(f"[{eid}:")[1]
                            else ""
                        )

                        # Verify it's a full digest, not truncated
                        assert (
                            len(token_part) > 20
                        ), f"Event {eid} has truncated token: {token_part}"
                        assert (
                            len(token_part) >= 32
                        ), f"Event {eid} token too short: {len(token_part)} chars"

                        # For commitments, verify it matches the expected CID
                        if token_part.startswith("test_digest"):
                            assert (
                                token_part == expected_cid
                            ), f"CID mismatch for event {eid}: expected {expected_cid}, got {token_part}"
                        else:
                            # For reflections, verify it matches the actual memegraph digest
                            actual_digest = memegraph.event_digest(eid)
                            assert token_part == str(
                                actual_digest
                            ), f"Token mismatch for event {eid}"
                        break

        finally:
            os.unlink(db_path)

    def test_no_digest_truncation_in_context(self):
        """Test that _short_digest() no longer truncates digests."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Initialize components
            eventlog = EventLog(db_path)
            memegraph = MemeGraphProjection(eventlog)

            # Add reflection event
            eid = eventlog.append(
                kind="reflection",
                content="Test reflection with apostrophe: it's working",
            )

            # Build context
            context = build_context_from_ledger(
                eventlog, memegraph=memegraph, include_reflections=True, n_reflections=3
            )

            # Find the reflection in context (enhanced format includes content)
            # Look for either [eid:token] or token=... format
            event_found = f"[{eid}:" in context or "token=" in context
            assert (
                event_found
            ), f"Event ID {eid} not found in context. Context preview: {context[:200]}..."

            # Extract token from enhanced format
            token_part = None
            for line in context.split("\n"):
                if "token=" in line and str(eid) in line:
                    # Enhanced format: token=... | content: ...
                    token_match = (
                        line.split("token=")[1].split(" |")[0]
                        if " |" in line
                        else line.split("token=")[1]
                    )
                    token_part = token_match.strip()
                    break
                elif f"[{eid}:" in line:
                    # Standard format: [eid:token]
                    token_part = (
                        line.split(f"[{eid}:")[1].split("]")[0]
                        if "]" in line.split(f"[{eid}:")[1]
                        else ""
                    )
                    break

            assert token_part is not None, f"Could not extract token for event {eid}"
            actual_digest = memegraph.event_digest(eid)

            assert len(token_part) > 20, f"Digest still truncated: {token_part}"
            assert token_part == str(
                actual_digest
            ), f"Digest doesn't match memegraph: {token_part} vs {actual_digest}"

        finally:
            os.unlink(db_path)

    def test_commitment_cid_no_truncation(self):
        """Test that commitment CIDs are not truncated to 8 characters."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Initialize components
            eventlog = EventLog(db_path)
            memegraph = MemeGraphProjection(eventlog)

            # Add commitment with full CID
            full_cid = "abcd1234567890efghijklmnopqrstuvwxyz"
            eid = eventlog.append(
                kind="commitment_open",
                content="Test commitment content",
                meta={"cid": full_cid},
            )

            # Build context
            context = build_context_from_ledger(
                eventlog, memegraph=memegraph, include_commitments=True, n_reflections=0
            )

            # Find the commitment in context
            assert f"[{eid}:" in context, "Commitment not found in context"

            # Extract CID from context
            line_with_commitment = None
            for line in context.split("\n"):
                if f"[{eid}:" in line:
                    line_with_commitment = line
                    break

            assert line_with_commitment is not None, "Commitment not found in context"

            # Verify full CID is present (not truncated to 8 chars)
            cid_part = (
                line_with_commitment.split(f"[{eid}:")[1].split("]")[0]
                if "]" in line_with_commitment.split(f"[{eid}:")[1]
                else ""
            )

            assert len(cid_part) > 8, f"CID still truncated to 8 chars: {cid_part}"
            assert (
                cid_part == full_cid
            ), f"CID doesn't match original: {cid_part} vs {full_cid}"

        finally:
            os.unlink(db_path)

    def test_special_characters_escaped_properly(self):
        """Test that special characters in content don't break token formatting."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Initialize components
            eventlog = EventLog(db_path)
            memegraph = MemeGraphProjection(eventlog)

            # Add events with various special characters
            special_content_events = [
                ("reflection", 'Content with "double quotes" and apostrophes'),
                ("reflection", "Content with \n newlines and \t tabs"),
                ("reflection", "Content with [brackets] and {braces}"),
                ("reflection", "Content with backslashes \\ and forward slashes /"),
            ]

            for kind, content in special_content_events:
                eid = eventlog.append(kind=kind, content=content)

                # Build context
                context = build_context_from_ledger(
                    eventlog,
                    memegraph=memegraph,
                    include_reflections=True,
                    n_reflections=1,
                )

                # Verify token format is not broken by special characters
                # Look for either [eid:token] or token=... format (enhanced)
                event_found = f"[{eid}:" in context or "token=" in context
                assert (
                    event_found
                ), f"Event {eid} not found in context. Context preview: {context[:200]}..."

                # Extract token from enhanced format
                token_part = None
                for line in context.split("\n"):
                    if "token=" in line and str(eid) in line:
                        # Enhanced format: token=... | content: ...
                        token_match = (
                            line.split("token=")[1].split(" |")[0]
                            if " |" in line
                            else line.split("token=")[1]
                        )
                        token_part = token_match.strip()
                        break
                    elif f"[{eid}:" in line:
                        # Standard format: [eid:token]
                        token_part = (
                            line.split(f"[{eid}:")[1].split("]")[0]
                            if "]" in line.split(f"[{eid}:")[1]
                            else ""
                        )
                        break

                assert (
                    token_part is not None
                ), f"Could not extract token for event {eid}"

                # Should have proper format and length
                assert (
                    len(token_part) > 20
                ), f"Token corrupted by special chars: {token_part}"
                assert (
                    len(token_part) >= 32
                ), f"Token too short due to special chars: {len(token_part)} chars"

        finally:
            os.unlink(db_path)

    def test_token_content_correlation(self):
        """Test that tokens are not truncated and have proper length."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Initialize components
            eventlog = EventLog(db_path)
            memegraph = MemeGraphProjection(eventlog)

            # Add events with different content types
            test_data = [
                ("reflection", "First test content"),
                (
                    "commitment_open",
                    "Second test content",
                    "commitment_cid_1234567890abcdef",
                ),
                ("reflection", "Third test content with apostrophe: it's fine"),
            ]

            event_ids = []
            for i, (kind, content, *extra) in enumerate(test_data):
                if kind == "commitment_open" and extra:
                    cid = extra[0]
                    eid = eventlog.append(kind=kind, content=content, meta={"cid": cid})
                    event_ids.append((eid, cid, "commitment"))
                else:
                    eid = eventlog.append(kind=kind, content=content)
                    digest = memegraph.event_digest(eid)
                    event_ids.append((eid, str(digest), "reflection"))

            # Build context
            context = build_context_from_ledger(
                eventlog,
                memegraph=memegraph,
                include_reflections=True,
                include_commitments=True,
                n_reflections=5,
            )

            # Verify all tokens are present and not truncated
            for eid, expected_token, event_type in event_ids:
                # Look for either [eid:token] or token=... format (enhanced)
                event_found = f"[{eid}:" in context or (
                    "token=" in context and str(eid) in context
                )
                assert event_found, f"Event {eid} missing from context"

                # Extract token from enhanced format
                token_part = None
                for line in context.split("\n"):
                    if "token=" in line and str(eid) in line:
                        # Enhanced format: token=... | content: ...
                        token_match = (
                            line.split("token=")[1].split(" |")[0]
                            if " |" in line
                            else line.split("token=")[1]
                        )
                        token_part = token_match.strip()
                        break
                    elif f"[{eid}:" in line:
                        # Standard format: [eid:token]
                        token_part = (
                            line.split(f"[{eid}:")[1].split("]")[0]
                            if "]" in line.split(f"[{eid}:")[1]
                            else ""
                        )
                        break

                assert (
                    token_part is not None
                ), f"Could not extract token for event {eid}"

                # Key test: Verify tokens are not truncated (the main fix)
                assert (
                    len(token_part) > 20
                ), f"Event {eid} has truncated token: {token_part}"

                if event_type == "commitment":
                    # Commitments should use the CID
                    assert (
                        token_part == expected_token
                    ), f"Commitment CID mismatch for {eid}"
                else:
                    # Reflections should use memegraph digest
                    assert (
                        len(token_part) >= 32
                    ), f"Reflection token too short: {len(token_part)} chars"

        finally:
            os.unlink(db_path)
