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
MANIFEST_V2_PATH = HERE / "manifest-v2.json"
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


class FixedRepliesAdapter:
    """Deterministic model substitute for the mechanistic experiment only."""

    supports_output_budget = False
    deterministic_latency_ms = 0
    model = "mechanistic-scripted"

    def __init__(self, replies: list[str], seed: int) -> None:
        self.replies = list(replies)
        self.seed = seed
        self.index = 0

    def generate_reply(self, system_prompt: str, user_prompt: str) -> GenerationResult:
        if self.index >= len(self.replies):
            raise RuntimeError("mechanistic reply sequence exhausted")
        reply = self.replies[self.index]
        self.index += 1
        return GenerationResult(
            text=reply,
            status="complete",
            meta={
                "provider": "scripted",
                "model": self.model,
                "temperature": 0,
                "seed": self.seed,
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


def _load_manifest_v2() -> dict[str, Any]:
    return json.loads(MANIFEST_V2_PATH.read_text(encoding="utf-8"))


def _new_log(path: Path, condition: str) -> EventLog:
    cls = EventLog if condition == "fallback" else NoFallbackEventLog
    return cls(str(path))


def _initialized_baseline(path: Path) -> None:
    """Create the one initialized ledger copied byte-for-byte into both arms."""
    log = EventLog(str(path))
    RuntimeLoop(eventlog=log, adapter=ScriptedAdapter(), autonomy=False)
    definitions = _load_manifest_v2()["mechanistic"]["initial_concept_definitions"]
    for definition in definitions:
        log.append(
            kind="concept_define",
            content=json.dumps(definition, sort_keys=True, separators=(",", ":")),
            meta={"source": "experiment_fixture"},
        )
    log._conn.close()


def _copy_baseline(baseline: Path, destination: Path, condition: str) -> EventLog:
    shutil.copy2(baseline, destination)
    return _new_log(destination, condition)


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


def _events_by_kind(events: Iterable[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [event for event in events if event["kind"] == kind]


def _commitment_cid(text: str) -> str:
    from hashlib import sha1

    return sha1(text.encode("utf-8")).hexdigest()[:8]


def protocol_gate(model: str | None = None) -> Path:
    """Measure one model configuration against PMM's existing protocol."""
    manifest = _load_manifest_v2()
    settings = manifest["protocol_gate"]
    selected_model = model or settings["default_model"]
    safe_model = "".join(ch if ch.isalnum() else "-" for ch in selected_model).strip("-")
    output = ARTIFACTS / f"protocol-gate-{safe_model}"
    if output.exists():
        raise SystemExit(f"refusing to overwrite protocol gate: {output}")
    output.mkdir(parents=True)
    shutil.copy2(MANIFEST_V2_PATH, output / "manifest-v2.json")

    trials: list[dict[str, Any]] = []
    expected_cid = _commitment_cid(settings["commitment_text"])
    for trial_number in range(1, int(settings["trials"]) + 1):
        db_path = output / f"trial-{trial_number:02d}.db"
        prompt_path = output / f"trial-{trial_number:02d}-prompts.json"
        log = EventLog(str(db_path))
        log.append(
            kind="concept_define",
            content=json.dumps(
                {
                    "token": "protocol.compatibility",
                    "concept_kind": "protocol",
                    "definition": "Compatibility with PMM's model-agnostic control protocol",
                    "attributes": {},
                    "version": "1.0",
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            meta={"source": "experiment_fixture"},
        )
        inner = OllamaAdapter(
            model=selected_model,
            output_budget_tokens=settings["output_budget_tokens"],
            output_budget_source="experiment_manifest_v2",
        )
        adapter = CapturingAdapter(inner, prompt_path)
        loop = RuntimeLoop(
            eventlog=log,
            adapter=adapter,
            autonomy=False,
            output_budget_tokens=settings["output_budget_tokens"],
            output_budget_source="experiment_manifest_v2",
        )
        loop.run_turn(settings["open_prompt"])
        first_events = log.read_all()
        first_assistant = _events_by_kind(first_events, "assistant_message")[-1]
        first_line = first_assistant["content"].splitlines()[0] if first_assistant["content"] else ""
        try:
            first_json = json.loads(first_line)
            first_line_json_parsed = isinstance(first_json, dict)
        except (TypeError, json.JSONDecodeError):
            first_line_json_parsed = False

        opens = [
            event for event in _events_by_kind(first_events, "commitment_open")
            if event["meta"].get("cid") == expected_cid
        ]
        declared = [
            event for event in _binding_events(first_events)
            if event["meta"].get("binding_origin") == "model_declared"
        ]
        close_prompt = (
            "Return exactly this one line, with no Markdown or explanation:\n"
            f"CLOSE: {expected_cid}"
        )
        loop.run_turn(close_prompt)
        after_close = log.read_all()
        closes = [
            event for event in _events_by_kind(after_close, "commitment_close")
            if event["meta"].get("cid") == expected_cid
        ]
        loop.run_turn(settings["retrieval_prompt"])
        events = log.read_all()
        selections = [json.loads(e["content"]) for e in _events_by_kind(events, "retrieval_selection")]
        last_selection = selections[-1] if selections else {"selected": []}
        assertions = {
            "first_line_json_parsed": first_line_json_parsed,
            "model_declared_binding_created": bool(declared),
            "model_declared_origin_points_to_assistant": bool(declared)
            and all(
                event["meta"].get("origin_event_id") == first_assistant["id"]
                for event in declared
            ),
            "exact_commit_opened": bool(opens),
            "exact_close_closed": bool(closes),
            "later_raw_retrieval_nonempty": bool(last_selection.get("selected")),
            "ledger_integrity": _verify_chain(events),
        }
        trials.append(
            {
                "trial": trial_number,
                "database": str(db_path),
                "database_sha256": _sha_file(db_path),
                "first_response": first_assistant["content"],
                "declared_binding_count": len(declared),
                "opened_cid": expected_cid if opens else None,
                "closed_cid": expected_cid if closes else None,
                "last_retrieval_selection": last_selection,
                "assertions": assertions,
                "passed": all(assertions.values()),
            }
        )

    report = {
        "schema": "pmm.protocol_conformance_gate.v1",
        "protocol_owner": "PMM",
        "model": selected_model,
        "recorded_model_digest": (
            settings["recorded_model_digest"]
            if selected_model == settings["default_model"]
            else None
        ),
        "temperature": settings["temperature"],
        "seed": settings["seed"],
        "design_commit": manifest["design_commit"],
        "harness_commit": _git("rev-parse", "HEAD"),
        "trials": trials,
        "pass_count": sum(1 for trial in trials if trial["passed"]),
        "trial_count": len(trials),
        "passed_reliably": all(trial["passed"] for trial in trials),
    }
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report_path


def mechanistic_pilot() -> Path:
    """Run the amended deterministic fallback pilot with active retrieval."""
    manifest = _load_manifest_v2()
    settings = manifest["mechanistic"]
    # Pilot 01 is the failed undefined-token fixture run; pilot 02 validated the
    # corrected harness before this amendment was frozen. Both are retained.
    output = ARTIFACTS / "mechanistic-pilot-03"
    if output.exists():
        raise SystemExit(f"refusing to overwrite mechanistic pilot: {output}")
    output.mkdir(parents=True)
    shutil.copy2(MANIFEST_V2_PATH, output / "manifest-v2.json")
    baseline = output / "initial-ledger.db"
    _initialized_baseline(baseline)
    baseline_sha = _sha_file(baseline)

    conditions: dict[str, Any] = {}
    for condition in ("fallback", "no_fallback"):
        db_path = output / f"{condition}.db"
        log = _copy_baseline(baseline, db_path, condition)
        assert _sha_file(db_path) == baseline_sha
        adapter = CapturingAdapter(
            FixedRepliesAdapter(settings["replies"], settings["seed"]),
            output / f"{condition}-prompts.json",
        )
        loop = RuntimeLoop(eventlog=log, adapter=adapter, autonomy=False)
        ranges: list[dict[str, Any]] = []
        for item in settings["prompts"]:
            before = log.count()
            loop.run_turn(item["prompt"])
            ranges.append(
                {"label": item["label"], "first_id": before + 1, "last_id": log.count()}
            )
        events = log.read_all()
        selection_events = _events_by_kind(events, "retrieval_selection")
        probe_selection = json.loads(selection_events[-1]["content"])
        selected_ids = set(probe_selection["selected"])
        selected_labels = [
            item["label"]
            for item in ranges
            if any(item["first_id"] <= event_id <= item["last_id"] for event_id in selected_ids)
        ]
        bindings = _binding_events(events)
        conditions[condition] = {
            "database": str(db_path),
            "database_sha256": _sha_file(db_path),
            "ledger_integrity": _verify_chain(events),
            "turn_ranges": ranges,
            "probe_selection": probe_selection,
            "probe_selected_labels": selected_labels,
            "assistant_outputs": [
                event["content"] for event in _events_by_kind(events, "assistant_message")
            ],
            "binding_origin_counts": {
                origin: sum(
                    1 for event in bindings
                    if event["meta"].get("binding_origin") == origin
                )
                for origin in sorted(
                    {str(event["meta"].get("binding_origin")) for event in bindings}
                )
            },
            "suppressed_fallback_assertions": getattr(
                log, "suppressed_fallback_assertions", []
            ),
        }

    fallback_selected = conditions["fallback"]["probe_selection"]["selected"]
    no_fallback_selected = conditions["no_fallback"]["probe_selection"]["selected"]
    assertions = {
        "byte_identical_initial_ledgers": True,
        "both_ledgers_integral": all(
            condition["ledger_integrity"] for condition in conditions.values()
        ),
        "raw_retrieval_nonempty_both_arms": bool(fallback_selected)
        and bool(no_fallback_selected),
        "model_declared_bindings_both_arms": all(
            condition["binding_origin_counts"].get("model_declared", 0) >= 5
            for condition in conditions.values()
        ),
        "fallback_attribution_only_in_fallback_arm": conditions["fallback"][
            "binding_origin_counts"
        ].get(FALLBACK_ORIGIN, 0)
        > 0
        and conditions["no_fallback"]["binding_origin_counts"].get(
            FALLBACK_ORIGIN, 0
        )
        == 0,
        "identical_scripted_outputs": conditions["fallback"]["assistant_outputs"]
        == conditions["no_fallback"]["assistant_outputs"]
        == settings["replies"],
        "declared_relationship_retrieved_both_arms": all(
            "declared_relationship" in condition["probe_selected_labels"]
            for condition in conditions.values()
        ),
        "fallback_distractor_retrieved_only_with_fallback": (
            "fallback_distractor"
            in conditions["fallback"]["probe_selected_labels"]
            and "fallback_distractor"
            not in conditions["no_fallback"]["probe_selected_labels"]
        ),
    }
    report = {
        "schema": "pmm.continuity_fallback_mechanistic_pilot.v1",
        "design_commit": manifest["design_commit"],
        "harness_commit": _git("rev-parse", "HEAD"),
        "initial_ledger_sha256": baseline_sha,
        "conditions": conditions,
        "assertions": assertions,
        "passed": all(assertions.values()),
    }
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if not report["passed"]:
        raise SystemExit(f"mechanistic pilot failed; inspect {report_path}")
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        choices=("preflight", "pilot", "protocol-gate", "mechanistic-pilot"),
    )
    parser.add_argument("--model")
    args = parser.parse_args()
    if args.mode == "preflight":
        result = preflight()
    elif args.mode == "pilot":
        result = pilot()
    elif args.mode == "protocol-gate":
        result = protocol_gate(args.model)
    else:
        result = mechanistic_pilot()
    print(result)


if __name__ == "__main__":
    main()
