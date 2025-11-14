#!/usr/bin/env python3
# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski
#
# PMM — Telemetry-Enhanced Full Chat Exporter
# High-fidelity export combining readable transcript + verifiable telemetry.
# Produces a Markdown file ready for public or AI audit.

import sqlite3
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import textwrap
from collections import Counter


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def export_session():
    repo_root = Path(__file__).resolve().parent.parent
    db_path = repo_root / ".data" / "pmmdb" / "pmm.db"
    if not db_path.exists():
        print(f"[ERROR] PMM database not found at {db_path}")
        return

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"chat_session_{now}_telemetry.md"
    output_path = repo_root / filename

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, ts, kind, content, meta, prev_hash, hash
        FROM events
        ORDER BY id ASC
    """
    )
    rows = cursor.fetchall()
    conn.close()

    md = []
    md.append("# Persistent Mind Model — Full Telemetry Export\n")
    md.append(f"**Exported:** {now.replace('_',' ')} UTC\n")
    md.append("**Database:** `.data/pmmdb/pmm.db`\n")
    md.append("---\n")

    total = len(rows)
    breaks = []
    kinds = Counter()
    continuity_check = []

    chat_messages = []
    event_sections = []

    for eid, ts, kind, content, meta, prev_hash, hsh in rows:
        kinds[kind] += 1

        # Detect continuity breaks
        if continuity_check and prev_hash and prev_hash != continuity_check[-1]:
            breaks.append((eid, continuity_check[-1], prev_hash))
        continuity_check.append(hsh)

        event_md: list[str] = []
        event_md.append(f"### Event {eid} — `{kind}` ({ts})\n")
        event_md.append(f"- **Prev Hash:** `{prev_hash or '∅'}`  \n")
        event_md.append(f"- **Hash:** `{hsh or '∅'}`  \n")

        if meta.strip() and meta.strip() not in ("{}", "null", "NULL"):
            try:
                parsed = json.loads(meta)
                pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
                event_md.append(
                    f"<details><summary>Meta</summary>\n\n```json\n{pretty}\n```\n</details>\n"
                )
            except Exception:
                event_md.append(f"_Meta:_ {meta}\n")

        role = (
            "👤 **User:**"
            if kind == "user_message"
            else (
                "🤖 **Echo:**"
                if kind == "assistant_message"
                else (
                    "📊 **Metrics:**"
                    if "metrics" in kind
                    else (
                        "🧩 **Coherence/Policy:**"
                        if kind
                        in {
                            "coherence_check",
                            "policy_update",
                            "meta_policy_update",
                            "stability_metrics",
                        }
                        else (
                            "🪞 **Reflection:**"
                            if kind == "reflection"
                            else "⚙️ **System:**"
                        )
                    )
                )
            )
        )

        event_md.append(
            f"\n{role}\n\n```text\n{textwrap.dedent(content).strip()}\n```\n"
        )
        event_md.append("---\n")

        event_sections.append("".join(event_md))

        if kind in {"user_message", "assistant_message"}:
            visible_content = textwrap.dedent(content).strip()
            if kind == "assistant_message":
                hidden_prefixes = ("COMMIT:", "CLOSE:", "CLAIM:", "REFLECT:")
                visible_lines = [
                    line
                    for line in visible_content.splitlines()
                    if not line.startswith(hidden_prefixes)
                ]
                visible_content = "\n".join(visible_lines).strip()
            chat_messages.append((kind, ts, visible_content))

    # =====================
    # Phase 1: Chat Conversation Playback
    # =====================
    if chat_messages:
        md.append("\n## 💬 Conversation Playback\n\n")
        md.append(f"Total chat turns: {len(chat_messages)}\n\n")

        for idx, (kind, ts, content) in enumerate(chat_messages, start=1):
            header = "👤 User" if kind == "user_message" else "🤖 Assistant"
            md.append(f"### Turn {idx}: {header}\n")
            md.append(f"*{ts}*\n\n")
            md.append("```text\n")
            md.append(f"{content}\n")
            md.append("```\n\n")

    # =====================
    # Phase 2: Chat Transcript (Event Log)
    # =====================
    md.append("## 🧠 Full Chronological Transcript\n\n")
    md.extend(event_sections)

    # =====================
    # Phase 3: Telemetry Summary
    # =====================
    md.append("\n## 📡 Telemetry Summary\n\n")

    md.append(f"- **Total Events:** {total}\n")
    md.append(f"- **Event Types:** {len(kinds)}\n\n")

    md.append("| Kind | Count |\n|------|-------:|\n")
    for k, c in kinds.items():
        md.append(f"| {k} | {c} |\n")
    md.append("\n")

    if breaks:
        md.append("⚠️ **Continuity Breaks Detected:**\n\n")
        for eid, prev, actual in breaks:
            md.append(f"- Event {eid}: expected `{prev}` but saw `{actual}`\n")
    else:
        md.append("✅ **No hash continuity breaks detected.**\n")

    # Highlight latest adaptive metrics where available.
    latest_stability = None
    latest_coherence = None
    latest_policy_update = None
    latest_meta_policy = None
    for eid, ts, kind, content, meta, prev_hash, hsh in reversed(rows):
        if kind == "stability_metrics" and latest_stability is None:
            latest_stability = content
        elif kind == "coherence_check" and latest_coherence is None:
            latest_coherence = content
        elif kind == "policy_update" and latest_policy_update is None:
            latest_policy_update = content
        elif kind == "meta_policy_update" and latest_meta_policy is None:
            latest_meta_policy = content
        if (
            latest_stability
            and latest_coherence
            and latest_policy_update
            and latest_meta_policy
        ):
            break

    md.append("\n### 🧩 Adaptive Metrics Snapshot\n\n")
    if latest_stability:
        try:
            s = json.loads(latest_stability)
        except Exception:
            s = {}
        if isinstance(s, dict):
            md.append(f"- Latest stability_score: `{s.get('stability_score')}`\n")
    if latest_coherence:
        try:
            c = json.loads(latest_coherence)
        except Exception:
            c = {}
        if isinstance(c, dict):
            md.append(f"- Latest coherence_score: `{c.get('coherence_score')}`\n")
    if latest_policy_update:
        try:
            p = json.loads(latest_policy_update)
        except Exception:
            p = {}
        if isinstance(p, dict):
            md.append(f"- Latest policy changes: `{p.get('changes')}`\n")
    if latest_meta_policy:
        try:
            mp = json.loads(latest_meta_policy)
        except Exception:
            mp = {}
        if isinstance(mp, dict):
            md.append(f"- Latest meta-policy changes: `{mp.get('changes')}`\n")

    # =====================
    # Phase 4: Verification Manifest (JSON block)
    # =====================
    # JSON-safe manifest with stable fields
    last_hash = rows[-1][6] if rows else ""
    manifest = {
        "export_timestamp": now,
        "total_events": total,
        "event_type_counts": dict(kinds),
        "continuity_breaks": len(breaks),
        # Digest over the chain of event hashes (not prev_hash) for stability
        "sha256_full_digest": sha256("".join(r[6] or "" for r in rows)),
        "last_hash": last_hash,
    }

    md.append("\n## 🧾 Verification Manifest\n\n")
    md.append("```json\n")
    md.append(json.dumps(manifest, indent=2, ensure_ascii=False))
    md.append("\n```\n")

    md.append("\n---\n")
    md.append(
        "_End of telemetry-enhanced session export — verifiable and replay-compatible._\n"
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"[OK] Telemetry-rich session exported → {output_path}")


if __name__ == "__main__":
    export_session()
