#!/usr/bin/env python3
"""Run primer-v2 through the unchanged nonproduction conformance harness."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from experiments.concept_authorship_channel import conformance_harness as base


MANIFEST = HERE / "conformance_manifest_v2.json"
ARTIFACTS = HERE / "artifacts" / "conformance-02-primer-v2"


def _evaluate() -> Path:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    report_path = ARTIFACTS / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    criteria = manifest["acceptance_criteria"]
    banned = criteria["banned_output_fragments"]
    model_results = []
    accepted_negative_total = 0
    placeholder_copy_count = 0
    emitted_total = accepted_total = final_total = column_total = 0

    for model in report["models"]:
        explicit_positive = [
            trial
            for trial in model["trials"]
            if trial["group"] == "explicit" and trial["appropriate_use_expected"]
        ]
        explicit_abstention = next(
            trial
            for trial in model["trials"]
            if trial["group"] == "explicit" and not trial["appropriate_use_expected"]
        )
        spontaneous_positive = [
            trial
            for trial in model["trials"]
            if trial["group"] == "spontaneous" and trial["appropriate_use_expected"]
        ]
        spontaneous_negative = [
            trial
            for trial in model["trials"]
            if trial["group"] == "spontaneous" and not trial["appropriate_use_expected"]
        ]
        explicit_success = sum(trial["appropriate_behavior"] for trial in explicit_positive)
        spontaneous_success = sum(trial["appropriate_behavior"] for trial in spontaneous_positive)
        negative_success = sum(trial["appropriate_behavior"] for trial in spontaneous_negative)
        accepted_negative = sum(
            trial["parse_status"] == "accepted"
            for trial in [explicit_abstention, *spontaneous_negative]
        )
        accepted_negative_total += accepted_negative
        compatibility = criteria["compatible_model"]
        compatible = (
            explicit_success == compatibility["explicit_positive_success"]
            and explicit_abstention["appropriate_behavior"]
            and spontaneous_success >= compatibility["minimum_spontaneous_appropriate_success"]
            and negative_success == compatibility["ordinary_negative_abstention_success"]
        )
        emitted_total += model["emitted_control_count"]
        accepted_total += model["accepted_control_count"]
        final_total += model["final_line_compliance_when_emitted"]["success"]
        column_total += model["column_zero_compliance_when_emitted"]["success"]

        safe_name = "".join(
            character if character.isalnum() else "-" for character in model["model"]
        ).strip("-")
        outputs = json.loads((ARTIFACTS / f"{safe_name}-outputs.json").read_text())
        copies = sum(
            any(fragment in output["response"] for fragment in banned)
            for output in outputs
        )
        placeholder_copy_count += copies
        model_results.append(
            {
                "model": model["model"],
                "digest": model["digest"],
                "explicit_positive_success": explicit_success,
                "explicit_positive_total": len(explicit_positive),
                "explicit_abstention_success": explicit_abstention["appropriate_behavior"],
                "spontaneous_appropriate_success": spontaneous_success,
                "spontaneous_appropriate_total": len(spontaneous_positive),
                "ordinary_negative_abstention_success": negative_success,
                "ordinary_negative_abstention_total": len(spontaneous_negative),
                "accepted_negative_declarations": accepted_negative,
                "placeholder_copy_count": copies,
                "compatible": compatible,
            }
        )

    compatible_count = sum(result["compatible"] for result in model_results)
    global_checks = {
        "zero_accepted_negative_declarations": accepted_negative_total
        == criteria["global"]["accepted_negative_declarations"],
        "zero_placeholder_copying": placeholder_copy_count
        == criteria["global"]["placeholder_copy_count"],
        "all_emitted_controls_structurally_accepted": emitted_total == accepted_total,
        "all_emitted_controls_final_line": emitted_total == final_total,
        "all_emitted_controls_column_zero": emitted_total == column_total,
        "minimum_compatible_models": compatible_count
        >= criteria["global"]["minimum_compatible_models"],
    }
    evaluation = {
        "schema": "pmm.control_primer_v2_acceptance.v1",
        "manifest_sha256": sha256(MANIFEST.read_bytes()).hexdigest(),
        "criteria": criteria,
        "models": model_results,
        "global_counts": {
            "accepted_negative_declarations": accepted_negative_total,
            "placeholder_copy_count": placeholder_copy_count,
            "emitted_controls": emitted_total,
            "accepted_controls": accepted_total,
            "final_line_controls": final_total,
            "column_zero_controls": column_total,
            "compatible_models": compatible_count,
        },
        "global_checks": global_checks,
        "passed": all(global_checks.values()),
    }
    path = ARTIFACTS / "acceptance.json"
    path.write_text(json.dumps(evaluation, indent=2, sort_keys=True) + "\n")
    checks_path = ARTIFACTS / "SHA256SUMS.json"
    checks = json.loads(checks_path.read_text())
    checks[path.name] = sha256(path.read_bytes()).hexdigest()
    checks_path.write_text(json.dumps(checks, indent=2, sort_keys=True) + "\n")
    return path


def main() -> None:
    base.MANIFEST_PATH = MANIFEST
    base.ARTIFACTS = ARTIFACTS
    base.main()
    print(_evaluate())


if __name__ == "__main__":
    main()
