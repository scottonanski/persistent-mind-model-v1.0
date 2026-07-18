#!/usr/bin/env python3
"""Offline, nonproduction evaluator for the proposed PMM-CONTROL envelope."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus.json"
ARTIFACTS = HERE / "artifacts" / "offline-safety-01"
PREFIX = "PMM-CONTROL:"
SCHEMA = "pmm.control.v1"
MAX_ENVELOPE_BYTES = 4096
MAX_CONCEPTS = 3
MAX_TOKEN_LENGTH = 64
MIN_DEFINITION_LENGTH = 20
MAX_DEFINITION_LENGTH = 500
TOKEN_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
FENCE_PATTERN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


@dataclass(frozen=True)
class ParseResult:
    status: str
    reason: str | None = None
    concepts: tuple[str, ...] = ()
    definitions: tuple[tuple[str, str], ...] = ()
    channel: str | None = None


def _fence_states(lines: list[str]) -> list[bool]:
    """Return whether each line begins inside a deterministic Markdown fence."""
    states: list[bool] = []
    fence_char: str | None = None
    fence_length = 0
    for line in lines:
        states.append(fence_char is not None)
        match = FENCE_PATTERN.match(line)
        if not match:
            continue
        run = match.group(1)
        trailing = match.group(2)
        if fence_char is None:
            fence_char = run[0]
            fence_length = len(run)
        elif run[0] == fence_char and len(run) >= fence_length and not trailing.strip():
            fence_char = None
            fence_length = 0
    return states


def _legacy_concepts(text: str) -> tuple[str, ...] | None:
    first_line = text.splitlines()[0] if text.splitlines() else ""
    try:
        parsed = json.loads(first_line)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("concepts"), list):
        return None
    values = parsed["concepts"]
    if not values or not all(isinstance(value, str) for value in values):
        return None
    return tuple(value.strip() for value in values)


def parse_candidate(text: str, existing_concepts: set[str]) -> ParseResult:
    lines = text.splitlines()
    occurrences = [
        (index, line, line.find(PREFIX))
        for index, line in enumerate(lines)
        if PREFIX in line
    ]
    legacy = _legacy_concepts(text)
    if not occurrences:
        if legacy is None:
            return ParseResult(status="no_declaration")
        return _validate_declaration(
            concepts=list(legacy),
            definitions=[],
            existing_concepts=existing_concepts,
            channel="legacy_header",
        )
    if len(occurrences) != 1:
        return ParseResult(status="rejected", reason="MULTIPLE_CONTROLS")

    index, line, column = occurrences[0]
    if column != 0:
        return ParseResult(status="rejected", reason="CONTROL_NOT_COLUMN_ZERO")
    states = _fence_states(lines)
    if states[index]:
        return ParseResult(status="rejected", reason="CONTROL_IN_FENCE")
    final_index = next(
        (candidate for candidate in range(len(lines) - 1, -1, -1) if lines[candidate].strip()),
        None,
    )
    if index != final_index:
        return ParseResult(status="rejected", reason="CONTROL_NOT_FINAL")

    raw = line[len(PREFIX) :]
    if len(raw.encode("utf-8")) > MAX_ENVELOPE_BYTES:
        return ParseResult(status="rejected", reason="ENVELOPE_TOO_LARGE")
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return ParseResult(status="rejected", reason="INVALID_JSON")
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        return ParseResult(status="rejected", reason="INVALID_SCHEMA")
    unknown = set(payload) - {"schema", "concepts", "define"}
    if unknown:
        return ParseResult(status="rejected", reason="UNKNOWN_KEYS")
    concepts = payload.get("concepts")
    definitions = payload.get("define", [])
    if not isinstance(concepts, list) or not concepts or len(concepts) > MAX_CONCEPTS:
        return ParseResult(status="rejected", reason="INVALID_CONCEPTS")
    if not isinstance(definitions, list) or len(definitions) > MAX_CONCEPTS:
        return ParseResult(status="rejected", reason="INVALID_DEFINITIONS")
    result = _validate_declaration(
        concepts=concepts,
        definitions=definitions,
        existing_concepts=existing_concepts,
        channel="final_envelope",
    )
    if result.status != "accepted" or legacy is None:
        return result
    if tuple(legacy) != result.concepts:
        return ParseResult(status="rejected", reason="DUAL_CHANNEL_CONFLICT")
    return ParseResult(
        status="accepted",
        concepts=result.concepts,
        definitions=result.definitions,
        channel="legacy_header+final_envelope",
    )


def _validate_declaration(
    *,
    concepts: list[Any],
    definitions: list[Any],
    existing_concepts: set[str],
    channel: str,
) -> ParseResult:
    if not concepts or len(concepts) > MAX_CONCEPTS or not all(
        isinstance(token, str) for token in concepts
    ):
        return ParseResult(status="rejected", reason="INVALID_CONCEPTS")
    if len(set(concepts)) != len(concepts):
        return ParseResult(status="rejected", reason="DUPLICATE_CONCEPT")
    for token in concepts:
        if len(token) > MAX_TOKEN_LENGTH or not TOKEN_PATTERN.fullmatch(token):
            return ParseResult(status="rejected", reason="INVALID_TOKEN")

    parsed_definitions: list[tuple[str, str]] = []
    seen_definitions: set[str] = set()
    for item in definitions:
        if not isinstance(item, dict):
            return ParseResult(status="rejected", reason="INVALID_DEFINITIONS")
        if set(item) - {"token", "definition"}:
            return ParseResult(status="rejected", reason="UNKNOWN_DEFINITION_KEYS")
        token = item.get("token")
        definition = item.get("definition")
        if not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token):
            return ParseResult(status="rejected", reason="INVALID_TOKEN")
        if token in seen_definitions:
            return ParseResult(status="rejected", reason="DUPLICATE_DEFINITION")
        seen_definitions.add(token)
        if token in existing_concepts:
            return ParseResult(status="rejected", reason="REDEFINITION")
        if not isinstance(definition, str) or not (
            MIN_DEFINITION_LENGTH <= len(definition) <= MAX_DEFINITION_LENGTH
        ):
            return ParseResult(status="rejected", reason="INVALID_DEFINITION")
        parsed_definitions.append((token, definition))

    concept_set = set(concepts)
    if not seen_definitions <= concept_set:
        return ParseResult(status="rejected", reason="UNGROUNDED_DEFINITION")
    for token in concepts:
        if token not in existing_concepts and token not in seen_definitions:
            return ParseResult(status="rejected", reason="UNDEFINED_CONCEPT")

    return ParseResult(
        status="accepted",
        concepts=tuple(concepts),
        definitions=tuple(parsed_definitions),
        channel=channel,
    )


def simulate_apply(result: ParseResult, *, assistant_event_id: int = 9001) -> dict[str, Any]:
    """Simulate effective state without importing or mutating production PMM."""
    definitions: dict[str, str] = {}
    associations: set[tuple[str, str]] = set()
    assertions: set[tuple[str, str, int]] = set()
    for token, definition in result.definitions:
        definitions[token] = definition
    for token in result.concepts:
        for target in ("current_user", "current_assistant", "current_commitment"):
            associations.add((token, target))
            assertions.add((token, target, assistant_event_id))
    return {
        "definitions": sorted(definitions.items()),
        "effective_associations": sorted(associations),
        "attribution_assertions": [
            {
                "token": token,
                "target": target,
                "binding_origin": "model_declared",
                "origin_event_id": origin_event_id,
            }
            for token, target, origin_event_id in sorted(assertions)
        ],
    }


def _load_cases(corpus: dict[str, Any]) -> list[dict[str, Any]]:
    cases = list(corpus["cases"])
    for case in cases:
        if case.get("generator") == "oversized_definition":
            payload = {
                "schema": SCHEMA,
                "concepts": ["continuity.oversized"],
                "define": [
                    {
                        "token": "continuity.oversized",
                        "definition": "x" * (MAX_ENVELOPE_BYTES + 1),
                    }
                ],
            }
            case["text"] = "Response.\n" + PREFIX + json.dumps(
                payload, separators=(",", ":")
            )
    for source in corpus["historical_sources"]:
        path = ROOT / source["path"]
        actual = sha256(path.read_bytes()).hexdigest()
        if actual != source["sha256"]:
            raise SystemExit(f"historical source hash mismatch: {path}: {actual}")
        records = json.loads(path.read_text(encoding="utf-8"))
        for record in records:
            cases.append(
                {
                    "id": f"{source['id']}_turn_{record['absolute_turn']}",
                    "expected": source["expected"],
                    "text": record["assistant"],
                    "historical_source": source["id"],
                }
            )
    return cases


def main() -> None:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    existing = set(corpus["existing_concepts"])
    cases = _load_cases(corpus)
    records: list[dict[str, Any]] = []
    rejection_reasons: Counter[str] = Counter()
    true_positive = false_positive = true_negative = false_negative = 0
    idempotency_ok = True

    for case in cases:
        result = parse_candidate(case["text"], existing)
        expected = case["expected"]
        expected_accept = expected == "accepted"
        actual_accept = result.status == "accepted"
        if expected_accept and actual_accept:
            true_positive += 1
        elif not expected_accept and actual_accept:
            false_positive += 1
        elif expected_accept and not actual_accept:
            false_negative += 1
        else:
            true_negative += 1
        if result.status == "rejected" and result.reason:
            rejection_reasons[result.reason] += 1
        expected_reason = case.get("reason")
        reason_matches = expected_reason is None or expected_reason == result.reason
        first_state = simulate_apply(result) if actual_accept else None
        second_state = simulate_apply(result) if actual_accept else None
        idempotent = first_state == second_state
        idempotency_ok = idempotency_ok and idempotent
        records.append(
            {
                "id": case["id"],
                "expected": expected,
                "actual": result.status,
                "reason": result.reason,
                "expected_reason": expected_reason,
                "reason_matches": reason_matches,
                "concepts": list(result.concepts),
                "definitions": [dict(token=t, definition=d) for t, d in result.definitions],
                "channel": result.channel,
                "simulated_state": first_state,
                "idempotent": idempotent,
            }
        )

    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 1.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 1.0
    reason_mismatches = [record["id"] for record in records if not record["reason_matches"]]
    report = {
        "schema": "pmm.control_offline_safety_report.v1",
        "design_commit": corpus["design_commit"],
        "corpus_sha256": sha256(CORPUS.read_bytes()).hexdigest(),
        "candidate_limits": {
            "max_envelope_bytes": MAX_ENVELOPE_BYTES,
            "max_concepts": MAX_CONCEPTS,
            "max_token_length": MAX_TOKEN_LENGTH,
            "min_definition_length": MIN_DEFINITION_LENGTH,
            "max_definition_length": MAX_DEFINITION_LENGTH,
            "token_pattern": TOKEN_PATTERN.pattern,
        },
        "case_count": len(cases),
        "confusion": {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "true_negative": true_negative,
            "false_negative": false_negative,
        },
        "precision": precision,
        "recall": recall,
        "false_accepted_mutations": false_positive,
        "rejection_reasons": dict(sorted(rejection_reasons.items())),
        "reason_mismatches": reason_mismatches,
        "idempotency_ok": idempotency_ok,
        "passed": false_positive == 0 and false_negative == 0 and not reason_mismatches and idempotency_ok,
        "cases": records,
    }
    ARTIFACTS.mkdir(parents=True, exist_ok=False)
    report_path = ARTIFACTS / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    checksums = {
        "corpus.json": sha256(CORPUS.read_bytes()).hexdigest(),
        "offline_harness.py": sha256(Path(__file__).read_bytes()).hexdigest(),
        "report.json": sha256(report_path.read_bytes()).hexdigest(),
    }
    (ARTIFACTS / "SHA256SUMS.json").write_text(
        json.dumps(checksums, indent=2, sort_keys=True) + "\n"
    )
    print(report_path)
    if not report["passed"]:
        raise SystemExit("offline safety evaluation failed")


if __name__ == "__main__":
    main()
