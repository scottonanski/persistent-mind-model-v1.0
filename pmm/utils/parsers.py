"""
Deterministic text parsing utilities for PMM runtime.

NO REGEX ALLOWED in this module per CONTRIBUTING.md.
All parsing must be explicit, auditable, and deterministic.
"""

from __future__ import annotations

from datetime import datetime


def extract_event_ids(text: str) -> list[int]:
    """
    Extract event ID references from text using deterministic parsing.

    Matches patterns like:
    - "event 123"
    - "Event 456"
    - "ID: 789"
    - "id 012"

    Does NOT match:
    - "Event 2025-10-02" (ISO timestamp)
    - "event:" (no number)
    - "123" (standalone number without context)

    Args:
        text: Input text to scan

    Returns:
        List of event IDs found (deduplicated, sorted)
    """
    if not text:
        return []

    ids: set[int] = set()
    tokens = text.split()

    for i, token in enumerate(tokens):
        token_lower = token.lower()

        # Pattern: "event <number>" or "id <number>"
        if token_lower in ("event", "id") and i + 1 < len(tokens):
            next_token = tokens[i + 1]

            # Check if next token is a pure number (not a date)
            # Dates have hyphens like "2025-10-02"
            if "-" not in next_token and ":" not in next_token:
                # Try to parse as integer
                try:
                    event_id = int(next_token)
                    ids.add(event_id)
                except ValueError:
                    continue

        # Pattern: "ID: <number>" or "id: <number>"
        # Handle both "ID:" as single token and "ID:" with space before number
        elif token_lower.startswith("id:"):
            # Extract number after colon
            parts = token.split(":", 1)
            if len(parts) == 2 and parts[1].strip():
                try:
                    event_id = int(parts[1].strip())
                    ids.add(event_id)
                except ValueError:
                    continue
            # Also check if next token is the number ("ID:" followed by "100")
            elif i + 1 < len(tokens):
                try:
                    event_id = int(tokens[i + 1])
                    ids.add(event_id)
                except ValueError:
                    continue

    return sorted(ids)


def parse_commitment_refs(text: str) -> list[str]:
    """
    Extract commitment references in format "123:abc12345" or "CID abc12345".

    Args:
        text: Input text to scan

    Returns:
        List of commitment IDs (CIDs) found
    """
    if not text:
        return []

    cids: set[str] = set()
    tokens = text.split()

    for i, token in enumerate(tokens):
        # Pattern: "123:abc12345" (event_id:cid_prefix)
        if ":" in token:
            parts = token.split(":")
            if len(parts) == 2:
                event_part, cid_part = parts
                # Validate: event_part is 2-5 digits, cid_part is hex
                if (
                    event_part.isdigit()
                    and 2 <= len(event_part) <= 5
                    and _is_hex_string(cid_part)
                    and len(cid_part) >= 8
                ):
                    cids.add(cid_part)

        # Pattern: "CID abc12345"
        token_upper = token.upper()
        if token_upper == "CID" and i + 1 < len(tokens):
            next_token = tokens[i + 1]
            if _is_hex_string(next_token) and len(next_token) >= 8:
                cids.add(next_token)

    return sorted(cids)


def is_iso_timestamp(s: str) -> bool:
    """
    Check if string is an ISO 8601 timestamp.

    Examples:
    - "2025-10-02T18:17:58Z" -> True
    - "2025-10-02" -> True
    - "Event 123" -> False

    Args:
        s: String to check

    Returns:
        True if valid ISO timestamp
    """
    if not s:
        return False

    s = s.strip()

    # Quick heuristic: ISO timestamps contain hyphens
    if "-" not in s:
        return False

    # Try parsing with datetime
    try:
        # Handle both with and without time component
        if "T" in s:
            # Full ISO format
            datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            # Date only
            datetime.fromisoformat(s)
        return True
    except (ValueError, AttributeError):
        return False


def split_key_value(line: str, separator: str = ":") -> tuple[str, str]:
    """
    Split a line into key-value pair at first separator.

    Examples:
    - "Name: Alice" -> ("Name", "Alice")
    - "Status: open" -> ("Status", "open")
    - "URL: http://example.com:8080" -> ("URL", "http://example.com:8080")

    Args:
        line: Line to split
        separator: Separator character (default ":")

    Returns:
        Tuple of (key, value), both stripped. Returns ("", "") if no separator found.
    """
    if not line or separator not in line:
        return ("", "")

    parts = line.split(separator, 1)
    if len(parts) != 2:
        return ("", "")

    key = parts[0].strip()
    value = parts[1].strip()
    return (key, value)


def normalize_whitespace(text: str) -> str:
    """
    Normalize whitespace deterministically: collapse multiple spaces/tabs/newlines to single space.

    Args:
        text: Input text

    Returns:
        Text with normalized whitespace
    """
    if not text:
        return ""

    # Split on any whitespace, filter empty, rejoin with single space
    tokens = text.split()
    return " ".join(tokens)


def tokenize_alphanumeric(text: str) -> list[str]:
    """
    Extract alphanumeric tokens from text (deterministic, no regex).

    Splits on non-alphanumeric characters, preserves apostrophes in words.

    Args:
        text: Input text

    Returns:
        List of lowercase alphanumeric tokens
    """
    if not text:
        return []

    tokens: list[str] = []
    current_token: list[str] = []

    for char in text.lower():
        if char.isalnum() or char == "'":
            current_token.append(char)
        else:
            if current_token:
                tokens.append("".join(current_token))
                current_token = []

    # Don't forget last token
    if current_token:
        tokens.append("".join(current_token))

    return tokens


def extract_name_from_change_event(content: str) -> str | None:
    """
    Extract name from "Name changed to: <name>" pattern.

    Args:
        content: Event content text

    Returns:
        Extracted name, or None if pattern not found
    """
    if not content:
        return None

    content = content.strip()

    # Look for "Name changed to:" prefix (case-insensitive)
    prefix_variants = [
        "name changed to:",
        "Name changed to:",
        "NAME CHANGED TO:",
    ]

    for prefix in prefix_variants:
        if content.lower().startswith(prefix.lower()):
            # Extract everything after the prefix
            name = content[len(prefix) :].strip()
            if name:
                return name

    return None


def token_overlap_ratio(text1: str, text2: str) -> float:
    """
    Calculate token overlap ratio between two texts (Jaccard similarity).

    Used for commitment similarity matching.

    Args:
        text1: First text
        text2: Second text

    Returns:
        Overlap ratio [0.0, 1.0]
    """
    # Both empty = identical
    if not text1 and not text2:
        return 1.0

    # One empty, one not = no overlap
    if not text1 or not text2:
        return 0.0

    tokens1 = set(tokenize_alphanumeric(text1))
    tokens2 = set(tokenize_alphanumeric(text2))

    # Both have no tokens = identical (both whitespace/punctuation only)
    if not tokens1 and not tokens2:
        return 1.0

    # One has tokens, one doesn't = no overlap
    if not tokens1 or not tokens2:
        return 0.0

    intersection = tokens1 & tokens2
    union = tokens1 | tokens2

    if not union:
        return 0.0

    return len(intersection) / len(union)


def strip_markdown_formatting(text: str) -> str:
    """
    Remove markdown formatting characters deterministically.

    Removes: **, *, _, `, #, >

    Args:
        text: Markdown text

    Returns:
        Plain text with formatting removed
    """
    if not text:
        return ""

    # Remove fenced code blocks first (``` ... ```)
    result = _remove_code_blocks(text)

    # Remove inline formatting
    for char in ["*", "_", "`", "#", ">"]:
        result = result.replace(char, " ")

    # Normalize whitespace
    return normalize_whitespace(result)


def extract_first_sentence(text: str) -> str:
    """
    Extract first sentence from text (split on . ! ? or newline).

    Args:
        text: Input text

    Returns:
        First sentence
    """
    if not text:
        return ""

    text = text.strip()

    # Find first sentence terminator
    for i, char in enumerate(text):
        if char in ".!?\n":
            return text[:i].strip()

    # No terminator found, return whole text
    return text


def extract_commitment_claims(text: str) -> list[str]:
    """
    Extract commitment claims from LLM response text.

    Looks for patterns like:
    - "I committed to X"
    - "opened commitment X"
    - "commitment X was opened"
    - "I see a commitment... event ID 21"

    Args:
        text: LLM response text

    Returns:
        List of claimed commitments (text descriptions or event IDs)
    """
    if not text:
        return []

    text.lower()
    claims: list[str] = []

    # Split into sentences for easier parsing
    sentences = []
    current = []
    for char in text:
        if char in ".!?\n":
            if current:
                sentences.append("".join(current).strip())
                current = []
        else:
            current.append(char)
    if current:
        sentences.append("".join(current).strip())

    for sentence in sentences:
        sent_lower = sentence.lower()

        # Pattern: "committed to X"
        if "committed to" in sent_lower:
            idx = sent_lower.find("committed to")
            rest = sentence[idx + len("committed to") :].strip()
            # Extract until punctuation or newline
            claim = _extract_until_punctuation(rest)
            if claim:
                claims.append(claim.lower())

        # Pattern: "opened commitment X" or "open commitment X"
        if "open" in sent_lower and "commitment" in sent_lower:
            # Find "commitment" and extract what follows
            idx = sent_lower.find("commitment")
            rest = sentence[idx + len("commitment") :].strip()
            claim = _extract_until_punctuation(rest)
            if claim:
                claims.append(claim.lower())

        # Pattern: "commitment X was opened/created/recorded"
        if "commitment" in sent_lower and any(
            word in sent_lower
            for word in ["was opened", "is opened", "created", "recorded"]
        ):
            # Extract between "commitment" and the verb
            idx_commit = sent_lower.find("commitment")
            rest = sentence[idx_commit + len("commitment") :].strip()
            # Find the verb
            for verb in [
                "was opened",
                "is opened",
                "was created",
                "is created",
                "recorded",
            ]:
                if verb in rest.lower():
                    claim = rest[: rest.lower().find(verb)].strip()
                    if claim:
                        claims.append(claim.lower())
                    break

        # Pattern: "event ID 21" or "event id: 21"
        if "event" in sent_lower and "id" in sent_lower:
            tokens = sent_lower.split()
            for i, token in enumerate(tokens):
                if token == "event" and i + 1 < len(tokens):
                    next_token = tokens[i + 1]
                    if next_token.startswith("id"):
                        # Look for number after "id"
                        if i + 2 < len(tokens) and tokens[i + 2].isdigit():
                            claims.append(tokens[i + 2])
                        # Or "id:123" format
                        elif ":" in next_token:
                            parts = next_token.split(":")
                            if len(parts) > 1 and parts[1].isdigit():
                                claims.append(parts[1])

        # Pattern: "focused on X"
        if "focused on" in sent_lower:
            idx = sent_lower.find("focused on")
            rest = sentence[idx + len("focused on") :].strip()
            claim = _extract_until_punctuation(rest)
            if claim:
                claims.append(claim.lower())

    return claims


def _extract_until_punctuation(text: str) -> str:
    """Extract text until punctuation or quote."""
    if not text:
        return ""

    result = []
    for char in text:
        if char in ".,;!?\"'":
            break
        result.append(char)

    return "".join(result).strip()


def extract_event_ids_from_evidence(text: str) -> list[int]:
    """
    Extract event IDs in format e#### from text.

    Args:
        text: Text containing event references like e1234

    Returns:
        List of event IDs (as integers)
    """
    if not text:
        return []

    eids: list[int] = []
    tokens = text.split()

    for token in tokens:
        # Look for e#### pattern
        if token.startswith("e") or token.startswith("E"):
            num_part = token[1:].strip("[](),;:.")
            if num_part.isdigit() and len(num_part) >= 2:
                try:
                    eids.append(int(num_part))
                except ValueError:
                    continue

    return eids


def extract_probe_sections(text: str) -> dict:
    """
    Extract sections from decision probe format.

    Expected format:
    - Observation: <text>
    - Inference: <text>
    - Evidence [e####, e####]
    - Next step: <text>
    - Test: <text>

    Args:
        text: Probe text

    Returns:
        Dict with keys: observation, inference, evidence, next_step, test
    """
    if not text:
        return {}

    sections = {}
    lines = text.split("\n")
    current_section = None
    current_content = []

    for line in lines:
        line_lower = line.lower().strip()

        # Check for section headers
        if line_lower.startswith("observation"):
            if current_section and current_content:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "observation"
            # Extract content after colon
            if ":" in line:
                current_content = [line.split(":", 1)[1].strip()]
            else:
                current_content = []
        elif "inference" in line_lower and ":" in line:
            if current_section and current_content:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "inference"
            current_content = [line.split(":", 1)[1].strip()]
        elif "evidence" in line_lower:
            if current_section and current_content:
                sections[current_section] = "\n".join(current_content).strip()
            sections["evidence"] = line
            current_section = None
            current_content = []
        elif line_lower.startswith("next") and "step" in line_lower:
            if current_section and current_content:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "next_step"
            if ":" in line:
                current_content = [line.split(":", 1)[1].strip()]
            else:
                current_content = []
        elif line_lower.startswith("test"):
            if current_section and current_content:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = "test"
            if ":" in line:
                current_content = [line.split(":", 1)[1].strip()]
            else:
                current_content = []
        elif current_section and line.strip():
            current_content.append(line)

    # Don't forget last section
    if current_section and current_content:
        sections[current_section] = "\n".join(current_content).strip()

    return sections


def tokenize_alnum(s: str) -> list[str]:
    """
    Tokenize text into lowercase alphanumeric tokens.

    Extracts only alphanumeric characters from each word.
    Used for commitment project ID generation and text matching.

    Args:
        s: Input text

    Returns:
        List of lowercase alphanumeric tokens

    Examples:
        >>> tokenize_alnum("Hello, World!")
        ['hello', 'world']
        >>> tokenize_alnum("test-123_foo")
        ['test123foo']
    """
    if not s:
        return []

    tokens = []
    for word in s.lower().split():
        # Extract only alphanumeric characters
        alnum_chars = [ch for ch in word if ch.isalnum()]
        if alnum_chars:
            tokens.append("".join(alnum_chars))

    return tokens


def split_non_alnum(s: str) -> list[str]:
    """
    Split text on non-alphanumeric characters deterministically.

    Similar to regex split(r"[^a-z0-9]+") but fully deterministic.
    Used for token-based similarity scoring.

    Args:
        s: Input text

    Returns:
        List of lowercase alphanumeric tokens

    Examples:
        >>> split_non_alnum("hello-world_test")
        ['hello', 'world', 'test']
        >>> split_non_alnum("foo123!bar456")
        ['foo123', 'bar456']
    """
    if not s:
        return []

    out = []
    current = []

    for ch in s.lower():
        if ch.isalnum():
            current.append(ch)
        else:
            if current:
                out.append("".join(current))
                current = []

    # Don't forget last token
    if current:
        out.append("".join(current))

    return out


def extract_closed_commitment_claims(text: str) -> list[str]:
    """
    Extract claims about closed commitments from text.

    Looks for patterns like:
    - "closed commitment [2674:6ffe0e34]"
    - "commitment 2468 is closed"
    - "[2674:6ffe0e34] closed"

    Args:
        text: LLM response text

    Returns:
        List of CID prefixes claimed to be closed
    """
    if not text:
        return []

    text.lower()
    claimed_closed: list[str] = []

    # Status keywords
    status_keywords = ["closed", "completed", "done"]

    # Split into tokens for easier parsing
    tokens = text.split()

    for i, token in enumerate(tokens):
        token_lower = token.lower()

        # Check if this token contains a status keyword
        if any(keyword in token_lower for keyword in status_keywords):
            # Look for commitment references nearby (within 5 tokens before/after)
            for j in range(max(0, i - 5), min(len(tokens), i + 6)):
                check_token = tokens[j]

                # Pattern: [2674:6ffe0e34]
                if "[" in check_token and ":" in check_token and "]" in check_token:
                    # Extract the CID part
                    start = check_token.find("[")
                    end = check_token.find("]")
                    if start < end:
                        ref = check_token[start + 1 : end]
                        parts = ref.split(":")
                        if len(parts) == 2 and _is_hex_string(parts[1]):
                            claimed_closed.append(parts[1][:8])

        # Also check for bracket format directly
        if "[" in token and ":" in token:
            # Extract commitment reference
            start = token.find("[")
            end = token.find("]") if "]" in token else len(token)
            ref = token[start + 1 : end]
            parts = ref.split(":")
            if len(parts) == 2 and _is_hex_string(parts[1]):
                cid_prefix = parts[1][:8]
                # Check if "closed" appears nearby
                for j in range(max(0, i - 3), min(len(tokens), i + 4)):
                    if any(keyword in tokens[j].lower() for keyword in status_keywords):
                        claimed_closed.append(cid_prefix)
                        break

    return list(set(claimed_closed))  # Deduplicate


# ---- Private helpers ----


def _is_hex_string(s: str) -> bool:
    """Check if string contains only hexadecimal characters."""
    if not s:
        return False

    for char in s.lower():
        if char not in "0123456789abcdef":
            return False

    return True


def _remove_code_blocks(text: str) -> str:
    """Remove fenced code blocks (``` ... ```) from text."""
    if not text or "```" not in text:
        return text

    # Simple state machine: toggle on/off with each ```
    result = []
    in_code_block = False
    i = 0

    while i < len(text):
        # Check for code block marker
        if text[i : i + 3] == "```":
            # Toggle code block state
            in_code_block = not in_code_block
            i += 3

            # Add a space separator when transitioning
            if not in_code_block:
                result.append(" ")

            continue

        # Only include text when NOT in a code block
        if not in_code_block:
            result.append(text[i])

        i += 1

    return "".join(result)
