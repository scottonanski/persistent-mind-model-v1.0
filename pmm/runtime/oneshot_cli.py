# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/runtime/oneshot_cli.py
"""Oneshot execution command line interface for PMM.

Enables programmatic, non-interactive execution of a single PMM turn.

WARNING: Calls against the same SQLite database MUST be serialized. Concurrent
invocations of pmm-turn on the same database can interleave event ranges, leading
to non-deterministic state tracking and integrity conflicts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional, Tuple

from pmm.core.event_log import EventLog
from pmm.runtime.loop import RuntimeLoop
from pmm.adapters import (
    resolve_application_output_budget,
)
from pmm.core.semantic_extractor import (
    extract_commitments,
    extract_closures,
    extract_claims,
    extract_reflect,
)


def resolve_provider_and_model(
    model: Optional[str],
    provider: Optional[str],
) -> Tuple[str, Optional[str]]:
    """Determine the resolved provider and model based on inputs and rules.

    Rules:
      - If model has prefix (e.g. openai:gpt-4), that determines the prefix provider.
      - Conflicting explicit provider and model prefix raises ValueError.
      - Explicit provider takes precedence if model is unprefixed.
      - Unprefixed model defaults deterministically to 'ollama' (ignores environment).
      - If neither provider nor model specifies it, fallback to PMM_PROVIDER or 'ollama'.
    """
    resolved_provider = provider
    resolved_model = model

    model_prefix = None
    if resolved_model and ":" in resolved_model:
        prefix_part, model_part = resolved_model.split(":", 1)
        if prefix_part.lower() in ("openai", "ollama", "dummy"):
            model_prefix = prefix_part.lower()
            resolved_model = model_part

    # Enforce consistency checks
    if resolved_provider and model_prefix and resolved_provider.lower() != model_prefix:
        raise ValueError(
            f"Conflict: Explicit provider '{resolved_provider}' does not match "
            f"model prefix '{model_prefix}' in '{model}'"
        )

    if not resolved_provider:
        if model_prefix:
            resolved_provider = model_prefix
        elif resolved_model:
            # Explicitly supplied unprefixed model deterministically means Ollama
            resolved_provider = "ollama"
        else:
            # Fallback to env PMM_PROVIDER, defaulting to 'ollama'
            env_provider = os.environ.get("PMM_PROVIDER")
            resolved_provider = env_provider.lower() if env_provider else "ollama"

    resolved_provider = resolved_provider.lower()
    if resolved_provider not in ("openai", "ollama", "dummy"):
        raise ValueError(f"Unknown or unsupported provider: {resolved_provider}")

    return resolved_provider, resolved_model


def instantiate_adapter(
    provider: str,
    model: Optional[str],
    output_budget_tokens: int | None = None,
    output_budget_source: str | None = None,
) -> Any:
    """Instantiate the adapter for the resolved provider and model."""
    if provider == "openai":
        from pmm.adapters.openai_adapter import OpenAIAdapter

        return OpenAIAdapter(
            model=model,
            output_budget_tokens=output_budget_tokens,
            output_budget_source=output_budget_source,
        )
    elif provider == "ollama":
        from pmm.adapters.ollama_adapter import OllamaAdapter

        return OllamaAdapter(
            model=model,
            output_budget_tokens=output_budget_tokens,
            output_budget_source=output_budget_source,
        )
    elif provider == "dummy":
        from pmm.adapters.dummy_adapter import DummyAdapter

        return DummyAdapter()
    raise ValueError(f"Unknown or unsupported provider: {provider}")


def run_one_turn(
    *,
    db_path: str,
    prompt: str,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    adapter: Optional[Any] = None,
    include_events: bool = False,
    output_budget_tokens: int | None = None,
) -> Dict[str, Any]:
    """Execute a single PMM turn synchronously and return structured updates."""
    if db_path != ":memory:":
        db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    with EventLog(db_path, mode="writer", writer_role="oneshot") as elog:
        return _run_one_turn_owned(
            elog=elog,
            prompt=prompt,
            model=model,
            provider=provider,
            adapter=adapter,
            include_events=include_events,
            output_budget_tokens=output_budget_tokens,
        )


def _run_one_turn_owned(
    *,
    elog: EventLog,
    prompt: str,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    adapter: Optional[Any] = None,
    include_events: bool = False,
    output_budget_tokens: int | None = None,
) -> Dict[str, Any]:
    """Run one turn while the caller retains fenced writer ownership."""

    # 1. Resolve LLM Adapter if not injected (for testing compatibility)
    if adapter is None:
        resolved_provider, resolved_model = resolve_provider_and_model(model, provider)
        if resolved_provider == "dummy":
            resolved_output_budget = None
            output_budget_source = "not_applicable"
        else:
            resolved_output_budget, output_budget_source = (
                resolve_application_output_budget(output_budget_tokens)
            )
        adapter = instantiate_adapter(
            resolved_provider,
            resolved_model,
            resolved_output_budget,
            output_budget_source,
        )
    elif output_budget_tokens is not None or os.environ.get(
        "PMM_OUTPUT_BUDGET_TOKENS"
    ) not in (None, ""):
        resolved_output_budget, output_budget_source = (
            resolve_application_output_budget(output_budget_tokens)
        )
    else:
        resolved_output_budget = getattr(adapter, "output_budget_tokens", None)
        output_budget_source = getattr(
            adapter, "output_budget_source", "adapter_capability_unknown"
        )

    # 2. Instantiate Loop (autonomy=False prevents background supervisor thread)
    loop = RuntimeLoop(
        eventlog=elog,
        adapter=adapter,
        autonomy=False,
        output_budget_tokens=resolved_output_budget,
        output_budget_source=output_budget_source,
    )

    # 3. Snapshot the actual tail event ID AFTER loop initialization
    tail_before = elog.read_tail(1)
    last_id_before = int(tail_before[-1]["id"]) if tail_before else 0

    # 4. Execute Turn
    loop.run_turn(prompt)

    # 5. Retrieve all events appended during this exact turn
    tail_after = elog.read_tail(1)
    last_id_after = int(tail_after[-1]["id"]) if tail_after else 0

    new_events = (
        elog.read_range(last_id_before + 1, last_id_after)
        if last_id_after > last_id_before
        else []
    )

    # 6. Extract results from actual newly appended events
    assistant_msg = next(
        (e for e in new_events if e["kind"] == "assistant_message"), None
    )
    generation_failure = next(
        (e for e in new_events if e["kind"] == "generation_failure"), None
    )

    assistant_raw = ""
    assistant_visible = ""
    if assistant_msg:
        assistant_raw = assistant_msg.get("content") or ""

        # Clean visible response (remove PMM markers)
        visible_lines = []
        for ln in assistant_raw.splitlines():
            if (
                extract_commitments([ln])
                or extract_closures([ln])
                or extract_reflect([ln]) is not None
            ):
                continue
            try:
                if extract_claims([ln]):
                    continue
            except ValueError:
                pass
            visible_lines.append(ln)
        assistant_visible = "\n".join(visible_lines).strip()

    # Extract opened CIDs from persisted event metadata
    opened_cids = [
        e["meta"].get("cid")
        for e in new_events
        if e["kind"] == "commitment_open"
        and isinstance(e.get("meta"), dict)
        and e["meta"].get("cid")
    ]

    # Extract closed CIDs from persisted event metadata
    closed_cids = [
        e["meta"].get("cid")
        for e in new_events
        if e["kind"] == "commitment_close"
        and isinstance(e.get("meta"), dict)
        and e["meta"].get("cid")
    ]

    # Extract validated claims from persisted events
    claims = []
    for e in new_events:
        if e["kind"] == "claim":
            meta = e.get("meta") or {}
            claim_type = meta.get("claim_type")
            content = e.get("content") or ""
            if "=" in content:
                try:
                    parts = content.split("=", 1)
                    claims.append({"type": claim_type, "data": json.loads(parts[1])})
                except Exception:
                    pass

    validation_failures = []
    for e in new_events:
        if e["kind"] != "validation_failure":
            continue
        try:
            failure_content = json.loads(e.get("content") or "{}")
        except Exception:
            failure_content = {"reason": e.get("content") or ""}
        validation_failures.append(
            {
                "event_id": e["id"],
                "claim_type": failure_content.get("claim_type"),
                "reason_code": failure_content.get("reason_code"),
                "reason": failure_content.get("reason"),
                "data": failure_content.get("data"),
            }
        )

    # Extract identity updates / summaries from persisted events
    identity_updates = []
    for e in new_events:
        if e["kind"] in ("identity_adoption", "summary_update", "meta_summary"):
            try:
                content_parsed = json.loads(e.get("content") or "{}")
            except Exception:
                content_parsed = e.get("content")
            identity_updates.append(
                {
                    "kind": e["kind"],
                    "content": content_parsed,
                    "meta": e.get("meta") or {},
                }
            )

    # Compile event range
    event_ids = [int(e["id"]) for e in new_events]
    event_range = {
        "first": min(event_ids) if event_ids else None,
        "last": max(event_ids) if event_ids else None,
    }

    output_data: Dict[str, Any] = {
        "assistant": assistant_visible,
        "assistant_raw": assistant_raw,
        "generation_status": (
            "complete"
            if assistant_msg
            else (
                (generation_failure.get("meta") or {}).get("status", "indeterminate")
                if generation_failure
                else "indeterminate"
            )
        ),
        "generation_failure": (
            {
                "status": (generation_failure.get("meta") or {}).get("status"),
                "partial_response": generation_failure.get("content") or "",
                "meta": generation_failure.get("meta") or {},
            }
            if generation_failure
            else None
        ),
        "event_range": event_range,
        "opened": opened_cids,
        "closed": closed_cids,
        "claims": claims,
        "validation_failures": validation_failures,
        "identity_updates": identity_updates,
    }

    if include_events:
        serialized_events = []
        for e in new_events:
            ev_dict = {
                "id": e["id"],
                "ts": e["ts"],
                "kind": e["kind"],
                "content": e["content"],
                "meta": e.get("meta") or {},
                "prev_hash": e["prev_hash"],
                "hash": e["hash"],
            }
            if e["kind"] in (
                "reflection",
                "summary_update",
                "autonomy_tick",
                "concept_bind_event",
                "retrieval_selection",
                "outcome_observation",
                "validation_failure",
            ):
                try:
                    ev_dict["content"] = json.loads(e["content"])
                except Exception:
                    pass
            serialized_events.append(ev_dict)
        output_data["events"] = serialized_events

    return output_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a single, non-interactive PMM turn and output strict JSON."
    )
    parser.add_argument(
        "--db",
        default=".data/pmmdb/pmm.db",
        help="Path to SQLite ledger database",
    )
    parser.add_argument(
        "--model",
        help="Specific model name (e.g. openai:gpt-4o-mini or ornith:9b)",
    )
    parser.add_argument(
        "--provider",
        help="Model provider override (dummy, ollama, openai)",
    )
    parser.add_argument(
        "--prompt",
        help="User prompt for the turn. If omitted, prompt is read from stdin.",
    )
    parser.add_argument(
        "--include-events",
        action="store_true",
        help="Include full generated event objects in JSON output",
    )
    parser.add_argument(
        "--output-budget-tokens",
        type=int,
        help="Provider-enforced maximum generated output tokens",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    prompt = args.prompt
    if prompt is None:
        try:
            prompt = sys.stdin.read()
        except KeyboardInterrupt:
            print(
                json.dumps({"error": "Prompt read interrupted by user"}),
                file=sys.stdout,
            )
            sys.exit(1)

    prompt = (prompt or "").strip()
    if not prompt:
        print(
            json.dumps({"error": "Prompt cannot be empty"}),
            file=sys.stdout,
        )
        print("Error: Prompt cannot be empty.", file=sys.stderr)
        sys.exit(1)

    try:
        results = run_one_turn(
            db_path=args.db,
            prompt=prompt,
            model=args.model,
            provider=args.provider,
            include_events=args.include_events,
            output_budget_tokens=args.output_budget_tokens,
        )
        print(json.dumps(results, indent=2), file=sys.stdout)
        sys.exit(0)
    except Exception as e:
        import traceback

        print(f"Error executing PMM turn: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

        print(json.dumps({"error": str(e)}), file=sys.stdout)
        sys.exit(1)


if __name__ == "__main__":
    main()
