#!/usr/bin/env python3
"""Provider-neutral, nonproduction PMM-CONTROL conformance experiment."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pmm.adapters.ollama_adapter import OllamaAdapter
from experiments.concept_authorship_channel.offline_harness import (
    PREFIX,
    parse_candidate,
)


HERE = Path(__file__).resolve().parent
MANIFEST_PATH = HERE / "conformance_manifest.json"
ARTIFACTS = HERE / "artifacts" / "conformance-01"


def _position_observations(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    occurrences = [
        {"line": index + 1, "column": line.find(PREFIX), "text": line}
        for index, line in enumerate(lines)
        if PREFIX in line
    ]
    final_index = next(
        (index for index in range(len(lines) - 1, -1, -1) if lines[index].strip()),
        None,
    )
    return {
        "occurrence_count": len(occurrences),
        "occurrences": occurrences,
        "sole_occurrence_is_final_nonempty": len(occurrences) == 1
        and final_index is not None
        and occurrences[0]["line"] == final_index + 1,
        "sole_occurrence_at_column_zero": len(occurrences) == 1
        and occurrences[0]["column"] == 0,
    }


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    existing = set(manifest["existing_concepts"])
    generation = manifest["generation"]
    if ARTIFACTS.exists():
        raise SystemExit(f"refusing to overwrite {ARTIFACTS}")
    ARTIFACTS.mkdir(parents=True)
    (ARTIFACTS / "manifest.json").write_bytes(MANIFEST_PATH.read_bytes())

    model_reports: list[dict[str, Any]] = []
    quality_items: list[dict[str, Any]] = []
    for model_spec in manifest["models"]:
        adapter = OllamaAdapter(
            model=model_spec["name"],
            output_budget_tokens=generation["output_budget_tokens"],
            output_budget_source="concept_authorship_conformance_manifest",
        )
        trial_reports: list[dict[str, Any]] = []
        raw_outputs: list[dict[str, Any]] = []
        for trial in manifest["trials"]:
            result = adapter.generate_reply(
                manifest["experimental_primer"], trial["prompt"]
            )
            parsed = parse_candidate(result.text, existing)
            position = _position_observations(result.text)
            required = set(trial["required_concepts"])
            structural_accept = parsed.status == "accepted"
            required_present = required <= set(parsed.concepts)
            appropriate_behavior = (
                structural_accept and required_present
                if trial["appropriate_use"]
                else parsed.status == "no_declaration"
            )
            trial_report = {
                "id": trial["id"],
                "group": trial["group"],
                "appropriate_use_expected": trial["appropriate_use"],
                "status": result.status,
                "parse_status": parsed.status,
                "rejection_reason": parsed.reason,
                "channel": parsed.channel,
                "concepts": list(parsed.concepts),
                "definitions": [
                    {"token": token, "definition": definition}
                    for token, definition in parsed.definitions
                ],
                "required_concepts_present": required_present,
                "appropriate_behavior": appropriate_behavior,
                "placement": position,
                "provider_meta": result.meta,
                "response_sha256": sha256(result.text.encode("utf-8")).hexdigest(),
            }
            trial_reports.append(trial_report)
            raw_outputs.append(
                {"id": trial["id"], "prompt": trial["prompt"], "response": result.text}
            )
            if trial["group"] == "spontaneous" and parsed.definitions:
                for token, definition in parsed.definitions:
                    blinded_id = sha256(
                        f"{model_spec['name']}:{trial['id']}:{token}".encode("utf-8")
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

        def _rate(group: str, expected: bool | None = None) -> tuple[int, int]:
            selected = [report for report in trial_reports if report["group"] == group]
            if expected is not None:
                selected = [
                    report
                    for report in selected
                    if report["appropriate_use_expected"] is expected
                ]
            return sum(1 for report in selected if report["appropriate_behavior"]), len(selected)

        explicit_ok, explicit_total = _rate("explicit")
        spontaneous_ok, spontaneous_total = _rate("spontaneous", True)
        abstain_ok, abstain_total = _rate("spontaneous", False)
        emitted = [
            report for report in trial_reports
            if report["placement"]["occurrence_count"] > 0
        ]
        model_reports.append(
            {
                "model": model_spec["name"],
                "digest": model_spec["digest"],
                "explicit_compliance": {"success": explicit_ok, "total": explicit_total},
                "spontaneous_appropriate_use": {
                    "success": spontaneous_ok,
                    "total": spontaneous_total,
                },
                "appropriate_abstention": {"success": abstain_ok, "total": abstain_total},
                "emitted_control_count": len(emitted),
                "accepted_control_count": sum(
                    1 for report in trial_reports if report["parse_status"] == "accepted"
                ),
                "final_line_compliance_when_emitted": {
                    "success": sum(
                        1 for report in emitted
                        if report["placement"]["sole_occurrence_is_final_nonempty"]
                    ),
                    "total": len(emitted),
                },
                "column_zero_compliance_when_emitted": {
                    "success": sum(
                        1 for report in emitted
                        if report["placement"]["sole_occurrence_at_column_zero"]
                    ),
                    "total": len(emitted),
                },
                "overuse_count": sum(
                    1
                    for report in trial_reports
                    if not report["appropriate_use_expected"]
                    and report["parse_status"] == "accepted"
                ),
                "trials": trial_reports,
            }
        )
        safe_name = "".join(
            character if character.isalnum() else "-"
            for character in model_spec["name"]
        ).strip("-")
        (ARTIFACTS / f"{safe_name}-outputs.json").write_text(
            json.dumps(raw_outputs, indent=2, sort_keys=True) + "\n"
        )

    report = {
        "schema": "pmm.control_conformance_report.v1",
        "protocol_is_provider_neutral": True,
        "manifest_sha256": sha256(MANIFEST_PATH.read_bytes()).hexdigest(),
        "models": model_reports,
        "quality_review_pending": bool(quality_items),
        "quality_item_count": len(quality_items),
    }
    report_path = ARTIFACTS / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    quality_items.sort(key=lambda item: item["blinded_id"])
    (ARTIFACTS / "blinded-quality-review.json").write_text(
        json.dumps(
            {
                "rubric": manifest["quality_rubric"],
                "items": quality_items,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    checksums = {
        path.name: sha256(path.read_bytes()).hexdigest()
        for path in sorted(ARTIFACTS.iterdir())
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    (ARTIFACTS / "SHA256SUMS.json").write_text(
        json.dumps(checksums, indent=2, sort_keys=True) + "\n"
    )
    print(report_path)


if __name__ == "__main__":
    main()
