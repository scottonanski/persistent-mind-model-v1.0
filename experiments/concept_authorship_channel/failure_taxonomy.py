#!/usr/bin/env python3
"""Classify preserved rejected controls without changing the candidate parser."""

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

from experiments.concept_authorship_channel.offline_harness import (
    MAX_CONCEPTS,
    MAX_TOKEN_LENGTH,
    PREFIX,
    SCHEMA,
    TOKEN_PATTERN,
)


SOURCES = (
    HERE / "artifacts" / "conformance-01",
    HERE / "artifacts" / "conformance-02-primer-v2",
)
OUTPUT = HERE / "artifacts" / "failure-taxonomy-01.json"
CATEGORIES = (
    "wrong_placement",
    "missing_or_incorrect_schema",
    "invalid_token",
    "missing_define_concepts_linkage",
    "placeholder_or_metasyntax_leakage",
    "invalid_json",
    "extra_keys",
    "other",
)
RESERVED_FRAGMENTS = (
    "namespace.token",
    "A precise relational definition of at least twenty characters",
)


def _control_line(response: str) -> str | None:
    lines = [line for line in response.splitlines() if PREFIX in line]
    return lines[0] if len(lines) == 1 else None


def _token_invalid(value: Any) -> bool:
    return not isinstance(value, str) or len(value) > MAX_TOKEN_LENGTH or not TOKEN_PATTERN.fullmatch(value)


def _payload_defects(
    response: str, payload: Any, existing: set[str]
) -> tuple[list[str], list[str]]:
    categories: set[str] = set()
    details: list[str] = []
    if not isinstance(payload, dict):
        return ["missing_or_incorrect_schema", "other"], [
            "top-level JSON value is not an object"
        ]

    if payload.get("schema") != SCHEMA:
        categories.add("missing_or_incorrect_schema")
        details.append("schema is absent or not pmm.control.v1")
    unknown = sorted(set(payload) - {"schema", "concepts", "define"})
    if unknown:
        categories.add("extra_keys")
        details.append(f"unknown top-level keys: {unknown}")
    if "object" in payload or any(fragment in response for fragment in RESERVED_FRAGMENTS):
        categories.add("placeholder_or_metasyntax_leakage")
        details.append("reserved example value or metasyntax-derived object wrapper appears")

    concepts = payload.get("concepts")
    definitions = payload.get("define", [])
    concept_tokens: list[str] = []
    if not isinstance(concepts, list) or not concepts or len(concepts) > MAX_CONCEPTS:
        categories.add("other")
        details.append("concepts is not a non-empty bounded array")
    else:
        concept_tokens = [value for value in concepts if isinstance(value, str)]
        if any(_token_invalid(value) for value in concepts):
            categories.add("invalid_token")
            details.append("concepts contains a token outside the allowed grammar")

    definition_tokens: list[str] = []
    definitions_structurally_valid = isinstance(definitions, list)
    if definitions_structurally_valid:
        for item in definitions:
            if not isinstance(item, dict):
                definitions_structurally_valid = False
                continue
            token = item.get("token")
            if _token_invalid(token):
                categories.add("invalid_token")
                details.append("define contains a token outside the allowed grammar")
            elif isinstance(token, str):
                definition_tokens.append(token)
    if not definitions_structurally_valid:
        categories.add("other")
        details.append("define is not an array of token/definition objects")

    if isinstance(concepts, list) and definitions_structurally_valid:
        new_concepts = {
            token for token in concept_tokens if not _token_invalid(token) and token not in existing
        }
        defined = set(definition_tokens)
        if new_concepts - defined:
            categories.add("missing_define_concepts_linkage")
            details.append(f"new concepts lack definitions: {sorted(new_concepts - defined)}")
        if defined - set(concept_tokens):
            categories.add("missing_define_concepts_linkage")
            details.append(f"definitions are not grounded in concepts: {sorted(defined - set(concept_tokens))}")

    return sorted(categories), details


def main() -> None:
    records: list[dict[str, Any]] = []
    primary_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    source_hashes: dict[str, str] = {}

    for source in SOURCES:
        manifest_path = source / "manifest.json"
        report_path = source / "report.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        report = json.loads(report_path.read_text(encoding="utf-8"))
        source_hashes[str(manifest_path.relative_to(HERE))] = sha256(manifest_path.read_bytes()).hexdigest()
        source_hashes[str(report_path.relative_to(HERE))] = sha256(report_path.read_bytes()).hexdigest()
        existing = set(manifest["existing_concepts"])

        for model in report["models"]:
            safe_name = "".join(
                character if character.isalnum() else "-" for character in model["model"]
            ).strip("-")
            outputs_path = source / f"{safe_name}-outputs.json"
            outputs = {item["id"]: item for item in json.loads(outputs_path.read_text())}
            source_hashes[str(outputs_path.relative_to(HERE))] = sha256(outputs_path.read_bytes()).hexdigest()
            for trial in model["trials"]:
                if trial["parse_status"] != "rejected":
                    continue
                response = outputs[trial["id"]]["response"]
                categories: set[str] = set()
                details: list[str] = []
                placement = trial["placement"]
                if (
                    placement["occurrence_count"] != 1
                    or not placement["sole_occurrence_is_final_nonempty"]
                    or not placement["sole_occurrence_at_column_zero"]
                    or trial["rejection_reason"] == "CONTROL_IN_FENCE"
                ):
                    categories.add("wrong_placement")
                    details.append("control occurrence violates unique/final/column-zero/outside-fence placement")

                line = _control_line(response)
                if line is None or not line.startswith(PREFIX):
                    if not categories:
                        categories.add("other")
                        details.append("no single column-zero control line available for structural analysis")
                else:
                    try:
                        payload = json.loads(line[len(PREFIX) :])
                    except json.JSONDecodeError as error:
                        categories.add("invalid_json")
                        details.append(f"JSON decode error: {error.msg}")
                        payload = None
                    if payload is not None:
                        found, found_details = _payload_defects(response, payload, existing)
                        categories.update(found)
                        details.extend(found_details)

                if not categories:
                    categories.add("other")
                    details.append("rejected for a defect outside the requested taxonomy")
                primary = trial["rejection_reason"] or "UNSPECIFIED"
                primary_counts[primary] += 1
                category_counts.update(categories)
                records.append(
                    {
                        "trial_set": source.name,
                        "model": model["model"],
                        "trial": trial["id"],
                        "primary_parser_reason": primary,
                        "categories": sorted(categories),
                        "details": details,
                        "response_sha256": trial["response_sha256"],
                    }
                )

    output = {
        "schema": "pmm.control_failure_taxonomy.v1",
        "scope": "all emitted controls rejected by the frozen candidate parser in conformance trials v1 and v2",
        "category_definitions": list(CATEGORIES),
        "source_sha256": source_hashes,
        "malformed_output_count": len(records),
        "primary_parser_reason_counts": dict(sorted(primary_counts.items())),
        "multi_label_category_counts": {
            category: category_counts[category] for category in CATEGORIES
        },
        "records": records,
    }
    OUTPUT.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
