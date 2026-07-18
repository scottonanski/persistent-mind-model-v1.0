#!/usr/bin/env python3
"""Nonproduction turn_ref safety corpus and Gemma v3 conformance experiment."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from pmm.adapters.ollama_adapter import OllamaAdapter
from experiments.concept_authorship_channel.conformance_harness import _position_observations
from experiments.concept_authorship_channel.offline_harness import (
    PREFIX,
    ParseResult,
    _fence_states,
    parse_candidate,
)


CORPUS = HERE / "turn_ref_corpus.json"
MANIFEST = HERE / "conformance_manifest_v3.json"
SAFETY_ARTIFACTS = HERE / "artifacts" / "turn-ref-safety-01"
CONFORMANCE_ARTIFACTS = HERE / "artifacts" / "conformance-03-turn-ref"


def parse_turn_ref(
    text: str, existing_concepts: set[str], expected_turn_ref: int
) -> ParseResult:
    """Validate placement and exact turn_ref, then delegate unchanged CTL rules."""
    lines = text.splitlines()
    occurrences = [
        (index, line, line.find(PREFIX))
        for index, line in enumerate(lines)
        if PREFIX in line
    ]
    if not occurrences:
        return ParseResult(status="no_declaration")
    if len(occurrences) != 1:
        return ParseResult(status="rejected", reason="MULTIPLE_CONTROLS")
    index, line, column = occurrences[0]
    if column != 0:
        return ParseResult(status="rejected", reason="CONTROL_NOT_COLUMN_ZERO")
    if _fence_states(lines)[index]:
        return ParseResult(status="rejected", reason="CONTROL_IN_FENCE")
    final_index = next(
        (candidate for candidate in range(len(lines) - 1, -1, -1) if lines[candidate].strip()),
        None,
    )
    if index != final_index:
        return ParseResult(status="rejected", reason="CONTROL_NOT_FINAL")
    try:
        payload = json.loads(line[len(PREFIX) :])
    except json.JSONDecodeError:
        return ParseResult(status="rejected", reason="INVALID_JSON")
    if not isinstance(payload, dict):
        return ParseResult(status="rejected", reason="INVALID_SCHEMA")
    if "turn_ref" not in payload:
        return ParseResult(status="rejected", reason="MISSING_TURN_REF")
    turn_ref = payload["turn_ref"]
    if not isinstance(turn_ref, int) or isinstance(turn_ref, bool) or turn_ref < 1:
        return ParseResult(status="rejected", reason="INVALID_TURN_REF")
    if turn_ref != expected_turn_ref:
        return ParseResult(status="rejected", reason="TURN_REF_MISMATCH")
    delegated = dict(payload)
    del delegated["turn_ref"]
    delegated_line = PREFIX + json.dumps(delegated, separators=(",", ":"))
    delegated_text = "\n".join([*lines[:index], delegated_line, *lines[index + 1 :]])
    return parse_candidate(delegated_text, existing_concepts)


def _write_checksums(directory: Path) -> None:
    checks = {
        path.name: sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.iterdir())
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    (directory / "SHA256SUMS.json").write_text(
        json.dumps(checks, indent=2, sort_keys=True) + "\n"
    )


def run_safety() -> dict[str, Any]:
    if SAFETY_ARTIFACTS.exists():
        raise SystemExit(f"refusing to overwrite {SAFETY_ARTIFACTS}")
    SAFETY_ARTIFACTS.mkdir(parents=True)
    (SAFETY_ARTIFACTS / "corpus.json").write_bytes(CORPUS.read_bytes())
    corpus = json.loads(CORPUS.read_text())
    existing = set(corpus["existing_concepts"])
    records = []
    false_accepts = reason_mismatches = 0
    for case in corpus["cases"]:
        result = parse_turn_ref(case["text"], existing, case["current_turn_ref"])
        expected = case["expected"]
        false_accept = expected != "accepted" and result.status == "accepted"
        reason_match = case.get("reason") is None or case["reason"] == result.reason
        false_accepts += false_accept
        reason_mismatches += not reason_match
        records.append(
            {
                "id": case["id"],
                "expected": expected,
                "actual": result.status,
                "reason": result.reason,
                "reason_matches": reason_match,
                "false_accepted_mutation": false_accept,
                "concepts": list(result.concepts),
                "definitions": [dict(token=t, definition=d) for t, d in result.definitions],
            }
        )
    report = {
        "schema": "pmm.control_turn_ref_safety_report.v1",
        "corpus_sha256": sha256(CORPUS.read_bytes()).hexdigest(),
        "case_count": len(records),
        "accepted_count": sum(record["actual"] == "accepted" for record in records),
        "false_accepted_mutations": false_accepts,
        "reason_mismatches": reason_mismatches,
        "reused_later_turn_mutations": sum(
            record["id"] == "reused_later_turn" and record["actual"] == "accepted"
            for record in records
        ),
        "passed": false_accepts == 0 and reason_mismatches == 0,
        "records": records,
    }
    (SAFETY_ARTIFACTS / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    _write_checksums(SAFETY_ARTIFACTS)
    return report


def run_conformance() -> Path:
    if CONFORMANCE_ARTIFACTS.exists():
        raise SystemExit(f"refusing to overwrite {CONFORMANCE_ARTIFACTS}")
    CONFORMANCE_ARTIFACTS.mkdir(parents=True)
    (CONFORMANCE_ARTIFACTS / "manifest.json").write_bytes(MANIFEST.read_bytes())
    manifest = json.loads(MANIFEST.read_text())
    model = manifest["model"]
    generation = manifest["generation"]
    adapter = OllamaAdapter(
        model=model["name"],
        output_budget_tokens=generation["output_budget_tokens"],
        output_budget_source="concept_authorship_turn_ref_v3_manifest",
    )
    existing = set(manifest["existing_concepts"])
    first_ref = manifest["turn_ref_allocation"]["first"]
    increment = manifest["turn_ref_allocation"]["increment"]
    trials: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    quality_items: list[dict[str, Any]] = []
    ordinal = 0
    for repetition in range(1, manifest["repetitions_per_prompt"] + 1):
        for trial in manifest["trials"]:
            turn_ref = first_ref + ordinal * increment
            ordinal += 1
            runtime_instruction = manifest["turn_ref_instruction"].format(turn_ref=turn_ref)
            system_prompt = manifest["experimental_primer"] + "\n\n" + runtime_instruction
            result = adapter.generate_reply(system_prompt, trial["prompt"])
            parsed = parse_turn_ref(result.text, existing, turn_ref)
            placement = _position_observations(result.text)
            required = set(trial["required_concepts"])
            required_present = required <= set(parsed.concepts)
            appropriate = (
                parsed.status == "accepted" and required_present
                if trial["appropriate_use"]
                else parsed.status == "no_declaration"
            )
            record = {
                "id": trial["id"],
                "repetition": repetition,
                "turn_ref": turn_ref,
                "group": trial["group"],
                "appropriate_use_expected": trial["appropriate_use"],
                "parse_status": parsed.status,
                "rejection_reason": parsed.reason,
                "concepts": list(parsed.concepts),
                "definitions": [dict(token=t, definition=d) for t, d in parsed.definitions],
                "required_concepts_present": required_present,
                "appropriate_behavior": appropriate,
                "placement": placement,
                "provider_meta": result.meta,
                "response_sha256": sha256(result.text.encode()).hexdigest(),
            }
            trials.append(record)
            outputs.append(
                {
                    "id": trial["id"],
                    "repetition": repetition,
                    "turn_ref": turn_ref,
                    "runtime_instruction": runtime_instruction,
                    "prompt": trial["prompt"],
                    "response": result.text,
                }
            )
            if trial["group"] == "spontaneous" and parsed.definitions:
                for token, definition in parsed.definitions:
                    blinded_id = sha256(
                        f"{trial['id']}:{repetition}:{turn_ref}:{token}".encode()
                    ).hexdigest()[:12]
                    quality_items.append(
                        {
                            "blinded_id": blinded_id,
                            "prompt": trial["prompt"],
                            "response_without_control": "\n".join(
                                line for line in result.text.splitlines()
                                if not line.startswith(PREFIX)
                            ),
                            "token": token,
                            "definition": definition,
                            "definition_relevance_score": None,
                            "relational_quality_score": None,
                            "judge_notes": None,
                        }
                    )
    positive = [trial for trial in trials if trial["appropriate_use_expected"]]
    negative = [trial for trial in trials if not trial["appropriate_use_expected"]]
    emitted_positive = [trial for trial in positive if trial["placement"]["occurrence_count"]]
    explicit_positive = [t for t in positive if t["group"] == "explicit"]
    explicit_negative = [t for t in negative if t["group"] == "explicit"]
    spontaneous_positive = [t for t in positive if t["group"] == "spontaneous"]
    spontaneous_negative = [t for t in negative if t["group"] == "spontaneous"]
    metrics = {
        "explicit_positive_success": sum(t["appropriate_behavior"] for t in explicit_positive),
        "explicit_positive_total": len(explicit_positive),
        "explicit_abstention_success": sum(t["appropriate_behavior"] for t in explicit_negative),
        "explicit_abstention_total": len(explicit_negative),
        "spontaneous_appropriate_success": sum(t["appropriate_behavior"] for t in spontaneous_positive),
        "spontaneous_appropriate_total": len(spontaneous_positive),
        "ordinary_negative_abstention_success": sum(t["appropriate_behavior"] for t in spontaneous_negative),
        "ordinary_negative_abstention_total": len(spontaneous_negative),
        "accepted_negative_controls": sum(t["parse_status"] == "accepted" for t in negative),
        "positive_emissions": len(emitted_positive),
        "accepted_positive_emissions": sum(t["parse_status"] == "accepted" for t in emitted_positive),
        "positive_turn_ref_rejections": sum(
            t["rejection_reason"] in {"MISSING_TURN_REF", "INVALID_TURN_REF", "TURN_REF_MISMATCH"}
            for t in positive
        ),
        "accepted_reserved_values": sum(
            t["parse_status"] == "accepted"
            and any("RESERVED" in value for value in [*t["concepts"], *(d["definition"] for d in t["definitions"])])
            for t in trials
        ),
    }
    criteria = manifest["acceptance_criteria"]["conformance"]
    structural_pass = (
        metrics["accepted_negative_controls"] == criteria["accepted_negative_controls"]
        and metrics["accepted_reserved_values"] == criteria["accepted_reserved_values"]
        and metrics["positive_turn_ref_rejections"] == criteria["positive_emissions_with_wrong_turn_ref"]
        and metrics["positive_emissions"] == metrics["accepted_positive_emissions"]
        and metrics["explicit_positive_success"] == criteria["explicit_positive_success"]
        and metrics["explicit_abstention_success"] == criteria["explicit_abstention_success"]
        and metrics["spontaneous_appropriate_success"] >= criteria["minimum_spontaneous_appropriate_success"]
        and metrics["ordinary_negative_abstention_success"] == criteria["ordinary_negative_abstention_success"]
    )
    report = {
        "schema": "pmm.control_conformance_report.v3",
        "manifest_sha256": sha256(MANIFEST.read_bytes()).hexdigest(),
        "protocol_is_provider_neutral": True,
        "model": model,
        "metrics": metrics,
        "structural_and_behavioral_pass": structural_pass,
        "quality_review_pending": bool(quality_items),
        "quality_item_count": len(quality_items),
        "parse_status_counts": dict(Counter(t["parse_status"] for t in trials)),
        "trials": trials,
    }
    (CONFORMANCE_ARTIFACTS / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    (CONFORMANCE_ARTIFACTS / "gemma4-cloud-outputs.json").write_text(
        json.dumps(outputs, indent=2, sort_keys=True) + "\n"
    )
    quality_items.sort(key=lambda item: item["blinded_id"])
    (CONFORMANCE_ARTIFACTS / "blinded-quality-review.json").write_text(
        json.dumps({"rubric": manifest["quality_rubric"], "items": quality_items}, indent=2, sort_keys=True) + "\n"
    )
    _write_checksums(CONFORMANCE_ARTIFACTS)
    return CONFORMANCE_ARTIFACTS / "report.json"


def main() -> None:
    safety = run_safety()
    if not safety["passed"]:
        raise SystemExit("turn_ref safety corpus failed; model calls not started")
    print(SAFETY_ARTIFACTS / "report.json")
    print(run_conformance())


if __name__ == "__main__":
    main()
