#!/usr/bin/env python3
"""Experiment-only harness for the universal continuity fallback ablation."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pmm.adapters import GenerationResult
from pmm.adapters.ollama_adapter import OllamaAdapter
from pmm.core.event_log import EventLog, _canonical_json
from pmm.runtime.loop import RuntimeLoop


HERE = Path(__file__).resolve().parent
MANIFEST_PATH = HERE / "manifest.json"
ARTIFACTS = HERE / "artifacts"
FALLBACK_ORIGIN = "runtime_continuity_fallback"


class NoFallbackEventLog(EventLog):
    """Suppress only universal fallback assertions inside this experiment."""

    def __init__(self, path: str = ":memory:") -> None:
        super().__init__(path)
        self.suppressed_fallback_assertions: list[dict[str, Any]] = []

    def append(
        self, *, kind: str, content: str, meta: dict[str, Any] | None = None
    ) -> int:
        if (
            kind in {"concept_bind_event", "concept_bind_thread"}
            and (meta or {}).get("binding_origin") == FALLBACK_ORIGIN
        ):
            self.suppressed_fallback_assertions.append(
                {"kind": kind, "content": content, "meta": dict(meta or {})}
            )
            return 0
        return super().append(kind=kind, content=content, meta=meta)


class CapturingAdapter:
    def __init__(self, inner: Any, capture_path: Path) -> None:
        self.inner = inner
        self.capture_path = capture_path
        self.calls: list[dict[str, Any]] = []
        for name in (
            "model",
            "supports_output_budget",
            "output_budget_tokens",
            "output_budget_source",
            "context_window_tokens",
            "deterministic_latency_ms",
        ):
            if hasattr(inner, name):
                setattr(self, name, getattr(inner, name))

    def generate_reply(self, system_prompt: str, user_prompt: str) -> GenerationResult:
        result = self.inner.generate_reply(system_prompt, user_prompt)
        self.calls.append(
            {
                "turn": len(self.calls) + 1,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "system_prompt_sha256": _sha_text(system_prompt),
                "system_prompt_chars": len(system_prompt),
                "response": result.text,
                "status": result.status,
                "provider_meta": result.meta,
            }
        )
        self.capture_path.write_text(
            json.dumps(self.calls, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return result


class ScriptedAdapter:
    supports_output_budget = False
    deterministic_latency_ms = 0
    model = "preflight-scripted"

    def __init__(self) -> None:
        self.index = 0
        self.replies = [
            "No declared concepts.\nCOMMIT: fallback_preflight_relation",
            (
                '{"concepts":["memory.persistence","identity.continuity"]}\n'
                "A declared relationship."
            ),
        ]

    def generate_reply(self, system_prompt: str, user_prompt: str) -> GenerationResult:
        reply = self.replies[self.index]
        self.index += 1
        return GenerationResult(
            text=reply,
            status="complete",
            meta={
                "provider": "scripted",
                "model": self.model,
                "temperature": 0,
                "seed": 1,
                "total_assembled_prompt_chars": len(system_prompt)
                + len(user_prompt),
            },
        )


def _sha_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _sha_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True
    ).strip()


def _load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _new_log(path: Path, condition: str) -> EventLog:
    cls = EventLog if condition == "fallback" else NoFallbackEventLog
    return cls(str(path))


def _binding_events(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        event
        for event in events
        if event["kind"] in {"concept_bind_event", "concept_bind_thread"}
    ]


def _verify_chain(events: list[dict[str, Any]]) -> bool:
    previous = None
    for event in events:
        payload = {
            "kind": event["kind"],
            "content": event["content"],
            "meta": event["meta"],
            "prev_hash": previous,
        }
        expected = sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
        if event["prev_hash"] != previous or event["hash"] != expected:
            return False
        previous = event["hash"]
    return True


def _normalized_nonbindings(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for event in events:
        if event["kind"] in {"concept_bind_event", "concept_bind_thread"}:
            continue
        meta = dict(event["meta"])
        meta.pop("about_event", None)
        telemetry = meta.get("prompt_telemetry")
        if isinstance(telemetry, dict):
            telemetry = dict(telemetry)
            telemetry.pop("rendered_pmm_context_chars", None)
            telemetry.pop("raw_evidence_chars", None)
            telemetry.pop("retrieval_provenance_chars", None)
            telemetry.pop("selected_evidence_events", None)
            meta["prompt_telemetry"] = telemetry
        normalized.append(
            {"kind": event["kind"], "content": event["content"], "meta": meta}
        )
    return normalized


def _first_turn(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    user_events_seen = 0
    result = []
    for event in events:
        if event["kind"] == "user_message":
            user_events_seen += 1
            if user_events_seen == 2:
                break
        result.append(event)
    return result


def _through_first_assistant(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for event in events:
        result.append(event)
        if event["kind"] == "assistant_message":
            break
    return result


def preflight() -> Path:
    output = ARTIFACTS / "preflight"
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    reports: dict[str, Any] = {}
    all_events: dict[str, list[dict[str, Any]]] = {}

    for condition in ("fallback", "no_fallback"):
        db_path = output / f"{condition}.db"
        capture = output / f"{condition}-prompts.json"
        log = _new_log(db_path, condition)
        adapter = CapturingAdapter(ScriptedAdapter(), capture)
        loop = RuntimeLoop(eventlog=log, adapter=adapter, autonomy=False)
        loop.run_turn("preflight fallback-only response")
        loop.run_turn("preflight model-declared response")
        events = log.read_all()
        all_events[condition] = events
        bindings = _binding_events(events)
        reports[condition] = {
            "database": str(db_path),
            "database_sha256": _sha_file(db_path),
            "event_count": len(events),
            "ledger_integrity": _verify_chain(events),
            "binding_origins": [e["meta"].get("binding_origin") for e in bindings],
            "bindings": [
                {"kind": e["kind"], "content": json.loads(e["content"]), "meta": e["meta"]}
                for e in bindings
            ],
            "suppressed_fallback_assertions": getattr(
                log, "suppressed_fallback_assertions", []
            ),
        }

    fallback_bindings = _binding_events(all_events["fallback"])
    no_fallback_bindings = _binding_events(all_events["no_fallback"])
    fallback_only = [
        event for event in fallback_bindings
        if event["meta"].get("binding_origin") == FALLBACK_ORIGIN
    ]
    declared_fallback = [
        event for event in fallback_bindings
        if event["meta"].get("binding_origin") == "model_declared"
    ]
    declared_no_fallback = [
        event for event in no_fallback_bindings
        if event["meta"].get("binding_origin") == "model_declared"
    ]
    assertions = {
        "both_ledgers_integral": all(r["ledger_integrity"] for r in reports.values()),
        "fallback_assertions_present": len(fallback_only) == 3,
        "no_fallback_assertions_absent": all(
            event["meta"].get("binding_origin") != FALLBACK_ORIGIN
            for event in no_fallback_bindings
        ),
        "model_declared_bindings_preserved": len(declared_fallback)
        == len(declared_no_fallback)
        == 4,
        # Inputs and semantic events match until the precise intervention
        # point. Projection differences after binding are expected outcomes.
        "pre_intervention_semantics_equal": _normalized_nonbindings(
            _through_first_assistant(all_events["fallback"])
        )
        == _normalized_nonbindings(
            _through_first_assistant(all_events["no_fallback"])
        ),
        "only_expected_writes_suppressed": len(
            reports["no_fallback"]["suppressed_fallback_assertions"]
        )
        == 3
        and all(
            item["kind"] in {"concept_bind_event", "concept_bind_thread"}
            and item["meta"].get("binding_origin") == FALLBACK_ORIGIN
            for item in reports["no_fallback"]["suppressed_fallback_assertions"]
        ),
    }
    report = {
        "schema": "pmm.continuity_fallback_preflight.v1",
        "design_commit": _load_manifest()["design_commit"],
        "harness_commit": _git("rev-parse", "HEAD"),
        "worktree_diff_sha256": _sha_text(_git("diff", "--binary")),
        "conditions": reports,
        "assertions": assertions,
        "passed": all(assertions.values()),
    }
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if not report["passed"]:
        raise SystemExit(f"preflight failed; inspect {report_path}")
    return report_path


def pilot() -> Path:
    manifest = _load_manifest()
    output = ARTIFACTS / "pilot-01"
    if output.exists():
        raise SystemExit(f"refusing to overwrite existing pilot: {output}")
    output.mkdir(parents=True)
    manifest_copy = output / "manifest.json"
    shutil.copy2(MANIFEST_PATH, manifest_copy)

    run_report: dict[str, Any] = {
        "schema": "pmm.continuity_fallback_pilot.v1",
        "design_commit": manifest["design_commit"],
        "harness_commit": _git("rev-parse", "HEAD"),
        "worktree_diff_sha256": _sha_text(_git("diff", "--binary")),
        "manifest_sha256": _sha_file(manifest_copy),
        "conditions": {},
    }
    settings = manifest["pilot"]
    for condition in ("fallback", "no_fallback"):
        db_path = output / f"{condition}.db"
        log = _new_log(db_path, condition)
        inner = OllamaAdapter(
            model=settings["model"],
            output_budget_tokens=settings["output_budget_tokens"],
            output_budget_source="experiment_manifest",
        )
        adapter = CapturingAdapter(inner, output / f"{condition}-prompts.json")
        loop = RuntimeLoop(
            eventlog=log,
            adapter=adapter,
            autonomy=settings["autonomy"],
            output_budget_tokens=settings["output_budget_tokens"],
            output_budget_source="experiment_manifest",
        )
        turn_ranges = []
        for item in manifest["scenario"]:
            before = log.count()
            loop.run_turn(item["prompt"])
            after = log.count()
            turn_ranges.append({"label": item["label"], "first_id": before + 1, "last_id": after})
        events = log.read_all()
        transcript = [
            {"id": e["id"], "kind": e["kind"], "content": e["content"], "meta": e["meta"]}
            for e in events
            if e["kind"] in {"user_message", "assistant_message", "generation_failure"}
        ]
        (output / f"{condition}-transcript.json").write_text(
            json.dumps(transcript, indent=2, sort_keys=True) + "\n"
        )
        selections = []
        for event in events:
            if event["kind"] == "retrieval_selection":
                selections.append({"event_id": event["id"], **json.loads(event["content"])})
        bindings = _binding_events(events)
        run_report["conditions"][condition] = {
            "database": str(db_path),
            "database_sha256": _sha_file(db_path),
            "ledger_integrity": _verify_chain(events),
            "event_count": len(events),
            "turn_ranges": turn_ranges,
            "retrieval_selections": selections,
            "binding_origin_counts": {
                origin: sum(1 for e in bindings if e["meta"].get("binding_origin") == origin)
                for origin in sorted({str(e["meta"].get("binding_origin")) for e in bindings})
            },
        }

    report_path = output / "report.json"
    report_path.write_text(json.dumps(run_report, indent=2, sort_keys=True) + "\n")
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "pilot"))
    args = parser.parse_args()
    result = preflight() if args.mode == "preflight" else pilot()
    print(result)


if __name__ == "__main__":
    main()
