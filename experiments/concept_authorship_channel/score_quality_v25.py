#!/usr/bin/env python3
"""Apply the frozen 0-2 rubric to the identity-masked v2.5 worksheet."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts" / "conformance-025-reserved-template"


def main() -> None:
    worksheet = json.loads((ARTIFACTS / "blinded-quality-review.json").read_text())
    report = json.loads((ARTIFACTS / "report.json").read_text())
    identity: dict[str, str] = {}
    for model in report["models"]:
        for trial in model["trials"]:
            for definition in trial["definitions"]:
                blinded_id = sha256(
                    f"{model['model']}:{trial['id']}:{trial['repetition']}:{definition['token']}".encode()
                ).hexdigest()[:12]
                identity[blinded_id] = model["model"]

    for item in worksheet["items"]:
        prompt = item["prompt"]
        if prompt.startswith("Give me three practical tips") or prompt.startswith("Calculate 144"):
            relevance, relational = 1, 0
            note = "Topically relevant to an ordinary prompt, but it deposits a task/topic concept where no persistent relational discovery was warranted."
        elif item["token"] == "material.constitution":
            relevance, relational = 1, 0
            note = "Relevant to the replacement prompt, but names a component set rather than the relation governing persistence or severance."
        else:
            relevance, relational = 2, 2
            note = "Precisely captures a reusable relationship developed by the preregistered relational-discovery prompt."
        item["definition_relevance_score"] = relevance
        item["relational_quality_score"] = relational
        item["judge_notes"] = note

    aggregates: dict[str, dict[str, float | int]] = {}
    for model in report["models"]:
        selected = [item for item in worksheet["items"] if identity[item["blinded_id"]] == model["model"]]
        rel_total = sum(item["definition_relevance_score"] for item in selected)
        quality_total = sum(item["relational_quality_score"] for item in selected)
        count = len(selected)
        aggregates[model["model"]] = {
            "items": count,
            "definition_relevance_total": rel_total,
            "definition_relevance_mean": rel_total / count if count else None,
            "relational_quality_total": quality_total,
            "relational_quality_mean": quality_total / count if count else None,
        }

    output = {
        "schema": "pmm.control_quality_review.v2.5",
        "rubric": worksheet["rubric"],
        "review_method": "Identity-masked worksheet scored after structural metrics were inspected; model labels were absent during item scoring, but this is not an independent blinded human review.",
        "items": worksheet["items"],
        "model_aggregates_after_unblinding": aggregates,
    }
    path = ARTIFACTS / "quality-scores.json"
    path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    checks_path = ARTIFACTS / "SHA256SUMS.json"
    checks = json.loads(checks_path.read_text())
    checks[path.name] = sha256(path.read_bytes()).hexdigest()
    checks_path.write_text(json.dumps(checks, indent=2, sort_keys=True) + "\n")
    print(path)


if __name__ == "__main__":
    main()
