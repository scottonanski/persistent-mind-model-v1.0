#!/usr/bin/env python3
"""Run the frozen repeated v2.5 reserved-template conformance condition."""

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
from experiments.concept_authorship_channel.offline_harness import PREFIX, parse_candidate


MANIFEST = HERE / "conformance_manifest_v25.json"
ARTIFACTS = HERE / "artifacts" / "conformance-025-reserved-template"


def _safe_name(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value).strip("-")


def _checksums() -> None:
    checks = {
        path.name: sha256(path.read_bytes()).hexdigest()
        for path in sorted(ARTIFACTS.iterdir())
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    (ARTIFACTS / "SHA256SUMS.json").write_text(
        json.dumps(checks, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if ARTIFACTS.exists():
        raise SystemExit(f"refusing to overwrite {ARTIFACTS}")
    ARTIFACTS.mkdir(parents=True)
    (ARTIFACTS / "manifest.json").write_bytes(MANIFEST.read_bytes())
    existing = set(manifest["existing_concepts"])
    copied_template = parse_candidate(manifest["reserved_template"], existing)
    reserved_token_probe = parse_candidate(
        'PMM-CONTROL:{"schema":"pmm.control.v1","concepts":["RESERVED"],'
        '"define":[{"token":"RESERVED","definition":"A sufficiently long probe definition value."}]}',
        existing,
    )
    reserved_definition_probe = parse_candidate(
        'PMM-CONTROL:{"schema":"pmm.control.v1","concepts":["template.probe"],'
        '"define":[{"token":"template.probe","definition":"RESERVED"}]}',
        existing,
    )
    template_preflight = {
        "verbatim_copy": {"status": copied_template.status, "reason": copied_template.reason},
        "reserved_token": {"status": reserved_token_probe.status, "reason": reserved_token_probe.reason},
        "reserved_definition": {
            "status": reserved_definition_probe.status,
            "reason": reserved_definition_probe.reason,
        },
    }
    if template_preflight != {
        "verbatim_copy": {"status": "rejected", "reason": "INVALID_TOKEN"},
        "reserved_token": {"status": "rejected", "reason": "INVALID_TOKEN"},
        "reserved_definition": {"status": "rejected", "reason": "INVALID_DEFINITION"},
    }:
        raise SystemExit(
            f"reserved template safety preflight failed: {template_preflight}"
        )
    generation = manifest["generation"]
    repetitions = manifest["repetitions_per_prompt"]
    reserved = set(manifest["reserved_values"].values())
    reports: list[dict[str, Any]] = []
    quality_items: list[dict[str, Any]] = []

    for model_spec in manifest["models"]:
        adapter = OllamaAdapter(
            model=model_spec["name"],
            output_budget_tokens=generation["output_budget_tokens"],
            output_budget_source="concept_authorship_conformance_v25_manifest",
        )
        trials: list[dict[str, Any]] = []
        outputs: list[dict[str, Any]] = []
        for repetition in range(1, repetitions + 1):
            for trial in manifest["trials"]:
                result = adapter.generate_reply(manifest["experimental_primer"], trial["prompt"])
                parsed = parse_candidate(result.text, existing)
                placement = _position_observations(result.text)
                required = set(trial["required_concepts"])
                required_present = required <= set(parsed.concepts)
                appropriate = (
                    parsed.status == "accepted" and required_present
                    if trial["appropriate_use"]
                    else parsed.status == "no_declaration"
                )
                contains_reserved = any(value in result.text for value in reserved)
                record = {
                    "id": trial["id"],
                    "repetition": repetition,
                    "group": trial["group"],
                    "appropriate_use_expected": trial["appropriate_use"],
                    "status": result.status,
                    "parse_status": parsed.status,
                    "rejection_reason": parsed.reason,
                    "concepts": list(parsed.concepts),
                    "definitions": [
                        {"token": token, "definition": definition}
                        for token, definition in parsed.definitions
                    ],
                    "required_concepts_present": required_present,
                    "appropriate_behavior": appropriate,
                    "contains_reserved_value": contains_reserved,
                    "placement": placement,
                    "provider_meta": result.meta,
                    "response_sha256": sha256(result.text.encode()).hexdigest(),
                }
                trials.append(record)
                outputs.append(
                    {
                        "id": trial["id"],
                        "repetition": repetition,
                        "prompt": trial["prompt"],
                        "response": result.text,
                    }
                )
                if trial["group"] == "spontaneous" and parsed.definitions:
                    for token, definition in parsed.definitions:
                        blinded_id = sha256(
                            f"{model_spec['name']}:{trial['id']}:{repetition}:{token}".encode()
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
        accepted_negative = [trial for trial in negative if trial["parse_status"] == "accepted"]
        negative_by_prompt = Counter(trial["id"] for trial in accepted_negative)
        explicit_positive = [trial for trial in positive if trial["group"] == "explicit"]
        explicit_negative = [trial for trial in negative if trial["group"] == "explicit"]
        spontaneous_positive = [trial for trial in positive if trial["group"] == "spontaneous"]
        spontaneous_negative = [trial for trial in negative if trial["group"] == "spontaneous"]
        criteria = manifest["acceptance_criteria"]["compatible_model"]
        metrics = {
            "explicit_positive_success": sum(t["appropriate_behavior"] for t in explicit_positive),
            "explicit_positive_total": len(explicit_positive),
            "explicit_abstention_success": sum(t["appropriate_behavior"] for t in explicit_negative),
            "explicit_abstention_total": len(explicit_negative),
            "spontaneous_appropriate_success": sum(t["appropriate_behavior"] for t in spontaneous_positive),
            "spontaneous_appropriate_total": len(spontaneous_positive),
            "ordinary_negative_abstention_success": sum(t["appropriate_behavior"] for t in spontaneous_negative),
            "ordinary_negative_abstention_total": len(spontaneous_negative),
            "accepted_negative_controls": len(accepted_negative),
            "accepted_negative_by_prompt": dict(sorted(negative_by_prompt.items())),
            "positive_emissions": len(emitted_positive),
            "accepted_positive_emissions": sum(t["parse_status"] == "accepted" for t in emitted_positive),
            "reserved_value_emissions": sum(t["contains_reserved_value"] for t in trials),
            "accepted_reserved_value_emissions": sum(
                t["contains_reserved_value"] and t["parse_status"] == "accepted" for t in trials
            ),
        }
        compatible = (
            metrics["explicit_positive_success"] == criteria["explicit_positive_success"]
            and metrics["explicit_abstention_success"] == criteria["explicit_abstention_success"]
            and metrics["spontaneous_appropriate_success"] >= criteria["minimum_spontaneous_appropriate_success"]
            and metrics["ordinary_negative_abstention_success"] == criteria["ordinary_negative_abstention_success"]
            and metrics["accepted_negative_controls"] == 0
            and metrics["positive_emissions"] == metrics["accepted_positive_emissions"]
            and metrics["accepted_reserved_value_emissions"] == 0
        )
        stop = manifest["acceptance_criteria"]["granite_stop_primer_iteration"]
        granite_stop = model_spec["name"].startswith("granite") and (
            len(accepted_negative) >= stop["accepted_negative_controls_at_least"]
            or max(negative_by_prompt.values(), default=0) >= stop["or_same_negative_prompt_accepted_at_least"]
        )
        reports.append(
            {
                "model": model_spec["name"],
                "digest": model_spec["digest"],
                "metrics": metrics,
                "compatible_before_quality_review": compatible,
                "granite_stop_primer_iteration": granite_stop,
                "trials": trials,
            }
        )
        (ARTIFACTS / f"{_safe_name(model_spec['name'])}-outputs.json").write_text(
            json.dumps(outputs, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    report = {
        "schema": "pmm.control_conformance_report.v2.5",
        "manifest_sha256": sha256(MANIFEST.read_bytes()).hexdigest(),
        "protocol_is_provider_neutral": True,
        "reserved_template_safety_preflight": template_preflight,
        "repetitions_per_prompt": repetitions,
        "models": reports,
        "quality_review_pending": bool(quality_items),
        "quality_item_count": len(quality_items),
    }
    (ARTIFACTS / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    quality_items.sort(key=lambda item: item["blinded_id"])
    (ARTIFACTS / "blinded-quality-review.json").write_text(
        json.dumps({"rubric": manifest["quality_rubric"], "items": quality_items}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _checksums()
    print(ARTIFACTS / "report.json")


if __name__ == "__main__":
    main()
