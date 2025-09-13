from __future__ import annotations

import argparse
from typing import Optional

from pmm.config import load_runtime_env
from pmm.storage.eventlog import EventLog
from pmm.runtime.introspection import build_prompt
from pmm.llm.factory import LLMFactory, LLMConfig
from pmm.bridge.manager import sanitize


def _gen_summary(chat, prompt: str, provider_family: Optional[str]) -> str:
    # Deterministic call: temp=0, bounded tokens
    messages = [{"role": "user", "content": prompt}]
    raw = chat.generate(messages, temperature=0.0, max_tokens=256)
    return sanitize(raw, family=provider_family)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pmm.cli.introspect",
        description="Log-only introspection: ask one question and append an introspection_report event.",
    )
    parser.add_argument("--topic", required=True, help="Introspection topic label")
    parser.add_argument("--scope", required=True, help="Introspection scope label")
    parser.add_argument(
        "--path",
        required=False,
        help="Optional path to the SQLite event log (defaults to PMM_DB or .data/pmm.db)",
    )
    args = parser.parse_args(argv)

    env = load_runtime_env()
    provider = env.provider
    model = env.model
    db_path = args.path or env.db_path

    # Build chat adapter via factory
    cfg = LLMConfig(provider=provider, model=model)
    bundle = LLMFactory.from_config(cfg)
    chat = bundle.chat

    # Build deterministic prompt and summary
    prompt = build_prompt(args.topic, args.scope)
    summary = _gen_summary(chat, prompt, provider)

    # Append a single log-only event
    evlog = EventLog(db_path)
    evlog.append(
        kind="introspection_report",
        content=summary,
        meta={"topic": args.topic, "scope": args.scope},
    )

    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
