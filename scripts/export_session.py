#!/usr/bin/env python3
# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""
PMM Chat Session Exporter

Exports the totality of the chat session, including messages, metrics, RSM (retrieval selections),
and replay commands, to a Markdown file in the repository root.

Usage: python scripts/export_session.py
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def export_session():
    repo_root = Path(__file__).resolve().parent.parent

    # Path to the PMM database
    db_path = repo_root / ".data" / "pmmdb" / "pmm.db"
    if not db_path.exists():
        print(f"Error: PMM database not found at {db_path}")
        return

    # Generate custom timestamp
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"chat_session_{now}.md"
    output_path = repo_root / filename

    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Query relevant events
    event_kinds = (
        "user_message",
        "assistant_message",
        "metrics_turn",
        "metrics_update",
        "autonomy_metrics",
        "retrieval_selection",  # Assuming RSM relates to retrieval selections; adjust if needed
        # Add 'replay_command' if there's a specific kind for replay commands
    )
    query = f"""
    SELECT ts, kind, content
    FROM events
    WHERE kind IN ({','.join(['?'] * len(event_kinds))})
    ORDER BY id
    """
    cursor.execute(query, event_kinds)
    events = cursor.fetchall()
    conn.close()

    # Format Markdown
    markdown = f"# Chat Session Export - {now.replace('_', ' ')}\n\n"

    sections = {
        "Chat Messages": ["user_message", "assistant_message"],
        "Metrics": ["metrics_turn", "metrics_update", "autonomy_metrics"],
        "RSM and Replay Commands": ["retrieval_selection"],  # Expand if more kinds
    }

    for section_title, kinds in sections.items():
        section_events = [e for e in events if e[1] in kinds]
        if section_events:
            markdown += f"## {section_title}\n\n"
            for ts, kind, content in section_events:
                markdown += (
                    f"- **[{kind.replace('_', ' ').title()}] {ts}**: {content}\n"
                )
            markdown += "\n"

    # Write to file
    with open(output_path, "w") as f:
        f.write(markdown)

    print(f"Session exported to {output_path}")


if __name__ == "__main__":
    export_session()
