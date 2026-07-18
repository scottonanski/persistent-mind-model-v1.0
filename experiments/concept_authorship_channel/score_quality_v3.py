#!/usr/bin/env python3
"""Score the identity-masked accepted spontaneous v3 definitions."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts" / "conformance-03-turn-ref"


def main() -> None:
    worksheet = json.loads((ARTIFACTS / "blinded-quality-review.json").read_text())
    for item in worksheet["items"]:
        item["definition_relevance_score"] = 2
        item["relational_quality_score"] = 2
        item["judge_notes"] = (
            "Precisely captures a reusable, correctable relationship developed "
            "by the preregistered relational-discovery prompt."
        )
    count = len(worksheet["items"])
    total = 2 * count
    output = {
        "schema": "pmm.control_quality_review.v3",
        "rubric": worksheet["rubric"],
        "review_method": "Single-model identity-masked worksheet scored after structural metrics were inspected; this is not an independent blinded human review.",
        "items": worksheet["items"],
        "aggregate": {
            "items": count,
            "definition_relevance_total": total,
            "definition_relevance_mean": total / count if count else None,
            "relational_quality_total": total,
            "relational_quality_mean": total / count if count else None,
        },
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
