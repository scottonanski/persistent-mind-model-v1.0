#!/usr/bin/env python3
# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Concept Token Layer (CTL) inspection tool.

Usage:
    python concept_inspect.py <ledger.db> list
    python concept_inspect.py <ledger.db> show <token>
    python concept_inspect.py <ledger.db> stats
    python concept_inspect.py <ledger.db> health
"""

import sys
import json
from pathlib import Path
from pmm.core.event_log import EventLog
from pmm.core.concept_graph import ConceptGraph
from pmm.core.concept_metrics import check_concept_health, compute_concept_metrics


def cmd_list(log: EventLog) -> None:
    """List all known concepts."""
    cg = ConceptGraph(log)
    cg.rebuild(log.read_all())

    if not cg.concepts:
        print("No concepts defined.")
        return

    print(f"\n=== Concepts ({len(cg.concepts)}) ===\n")

    # Group by prefix
    by_prefix = {}
    for token in sorted(cg.concepts.keys()):
        prefix = token.split(".")[0] if "." in token else "other"
        if prefix not in by_prefix:
            by_prefix[prefix] = []
        by_prefix[prefix].append(token)

    for prefix in sorted(by_prefix.keys()):
        print(f"{prefix}:")
        for token in by_prefix[prefix]:
            defn = cg.get_definition(token)
            events = cg.events_for_concept(token)
            count = len(events)
            if defn:
                snippet = (
                    defn.definition[:50] + "..."
                    if len(defn.definition) > 50
                    else defn.definition
                )
                print(f"  {token:40} {snippet:50} ({count} refs)")
            else:
                print(f"  {token:40} {'':50} ({count} refs)")
        print()


def cmd_show(log: EventLog, token: str) -> None:
    """Show detailed information for a concept token."""
    cg = ConceptGraph(log)
    cg.rebuild(log.read_all())

    canonical = cg.canonical_token(token)
    defn = cg.get_definition(canonical)

    if not defn:
        print(f"Concept '{token}' not found.")
        return

    print(f"\n=== Concept: {canonical} ===\n")
    print(f"Kind:       {defn.concept_kind}")
    print(f"Definition: {defn.definition}")
    print(f"Version:    {defn.version}")
    print(f"Defined at: event #{defn.event_id}")

    if defn.attributes:
        print(f"Attributes: {json.dumps(defn.attributes, indent=2)}")

    # Aliases
    aliases = [alias for alias, target in cg.aliases.items() if target == canonical]
    if aliases:
        print(f"\nAliases: {', '.join(aliases)}")

    # History
    history = cg.get_history(canonical)
    if len(history) > 1:
        print(f"\nVersion history: {len(history)} versions")
        for i, h in enumerate(history, 1):
            print(f"  v{i}: event #{h.event_id} - {h.definition[:40]}...")

    # Bound events
    events = cg.events_for_concept(canonical)
    print(f"\nBound events: {len(events)}")
    if events:
        print(f"  Event IDs: {', '.join(str(e) for e in events[:10])}")
        if len(events) > 10:
            print(f"  ... and {len(events) - 10} more")

    # Relations
    neighbors = cg.neighbors(canonical)
    if neighbors:
        print(f"\nRelated concepts: {len(neighbors)}")
        for n in neighbors[:10]:
            # Find relation type
            rels = []
            for from_tok, to_tok, rel in cg.concept_edges:
                if (from_tok == canonical and to_tok == n) or (
                    to_tok == canonical and from_tok == n
                ):
                    rels.append(rel)
            rel_str = ", ".join(set(rels))
            print(f"  {n} ({rel_str})")
        if len(neighbors) > 10:
            print(f"  ... and {len(neighbors) - 10} more")

    print()


def cmd_stats(log: EventLog) -> None:
    """Show concept layer statistics."""
    cg = ConceptGraph(log)
    cg.rebuild(log.read_all())

    stats = cg.stats()

    print("\n=== Concept Layer Statistics ===\n")
    print(f"Total concepts:     {stats['total_concepts']}")
    print(f"Total aliases:      {stats['total_aliases']}")
    print(f"Total edges:        {stats['total_edges']}")
    print(f"Total bindings:     {stats['total_bindings']}")
    print(f"Events with concepts: {stats['events_with_concepts']}")

    # Compute metrics
    metrics = compute_concept_metrics(log)

    print("\nConcept usage:")
    if metrics["concepts_used"]:
        # Top 10 by usage
        top = sorted(metrics["concepts_used"].items(), key=lambda x: (-x[1], x[0]))[:10]
        for token, count in top:
            print(f"  {token:40} {count:4} refs")

    if metrics["concept_gaps"]:
        print(
            f"\nConcepts with low evidence (< 2 refs): {len(metrics['concept_gaps'])}"
        )
        for token in metrics["concept_gaps"][:5]:
            print(f"  {token}")
        if len(metrics["concept_gaps"]) > 5:
            print(f"  ... and {len(metrics['concept_gaps']) - 5} more")

    if metrics["concept_conflicts"]:
        print(
            f"\nConcepts with conflicting relations: {len(metrics['concept_conflicts'])}"
        )
        for token in metrics["concept_conflicts"]:
            print(f"  {token}")

    print()


def cmd_health(log: EventLog) -> None:
    """Show concept layer health metrics."""
    health = check_concept_health(log)

    print("\n=== Concept Layer Health ===\n")
    print(f"Total concepts:         {health['total_concepts']}")
    print(f"Total bindings:         {health['total_bindings']}")
    print(f"Avg bindings/concept:   {health['avg_bindings_per_concept']}")
    print(f"Governance concepts:    {health['governance_concept_count']}")
    print(f"Concepts with gaps:     {health['gap_count']}")
    print(f"Concepts with conflicts: {health['conflict_count']}")
    print(f"\nHealth score:           {health['health_score']:.2f} / 1.00")

    if health["health_score"] >= 0.8:
        status = "HEALTHY"
    elif health["health_score"] >= 0.5:
        status = "MODERATE"
    else:
        status = "NEEDS ATTENTION"

    print(f"Status:                 {status}")
    print()


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    db_path = Path(sys.argv[1])
    if not db_path.exists():
        print(f"Error: Ledger not found: {db_path}")
        sys.exit(1)

    command = sys.argv[2]

    log = EventLog(str(db_path))

    if command == "list":
        cmd_list(log)
    elif command == "show":
        if len(sys.argv) < 4:
            print("Usage: concept_inspect.py <ledger.db> show <token>")
            sys.exit(1)
        token = sys.argv[3]
        cmd_show(log, token)
    elif command == "stats":
        cmd_stats(log)
    elif command == "health":
        cmd_health(log)
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
