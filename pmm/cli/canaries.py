from __future__ import annotations
import argparse

from pmm.storage.eventlog import EventLog
from pmm.runtime.canaries import run_canaries
from pmm.llm.factory import LLMConfig, build_chat


def main() -> None:
    ap = argparse.ArgumentParser(description="Run capability canaries (events-only).")
    ap.add_argument("--db", required=True, help="Path to ledger DB")
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--provider", default="openai")
    args = ap.parse_args()

    evlog = EventLog(args.db)
    chat = build_chat(LLMConfig(provider=args.provider, model=args.model))

    results = run_canaries(lambda p: chat(p))
    for r in results:
        evlog.append(
            kind="canary_result",
            content="",
            meta={"name": r["name"], "pass": bool(r["passed"])},
        )

    print(
        "canaries:",
        ", ".join(f"{r['name']}={'PASS' if r['passed'] else 'FAIL'}" for r in results),
    )


if __name__ == "__main__":
    main()
