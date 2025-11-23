# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/runtime/ctl_injector.py
"""Runtime module to identify and inject CTL tokens into the retrieval context.

This module implements the 'CTL Lookup Injector' pattern:
1. Watches the user query.
2. Identifies concept tokens involved (via lexical matching against the Graph).
3. Provides these tokens to the Retrieval Pipeline to ensure pointer-based dereference.
"""

from typing import Dict, List, Set
import re
from pmm.core.concept_graph import ConceptGraph


class CTLLookupInjector:
    """Identifies relevant CTL tokens from user queries to force memory injection."""

    def __init__(self, concept_graph: ConceptGraph) -> None:
        self.concept_graph = concept_graph
        # Deterministic synonym map for identity/authority prompts.
        self._synonym_map: Dict[str, List[str]] = {
            "creator": ["user.identity"],
            "author": ["user.identity"],
            "builder": ["user.identity"],
            "maker": ["user.identity"],
            "founder": ["user.identity"],
        }

    def extract_tokens(self, query_text: str) -> List[str]:
        """Identify concept tokens relevant to the query text.

        Uses a heuristic matching strategy:
        - Tokenizes query into words (ignoring punctuation).
        - Checks if the *suffix* (last part) of any known concept token appears in the query.
        - Checks if the *full token* appears in the query.

        Args:
            query_text: The raw user prompt.

        Returns:
            List of unique concept tokens found in the query.
        """
        if not query_text:
            return []

        query_lower = query_text.lower()
        # Use regex to extract alphanumeric words only
        query_words = set(re.findall(r"\w+", query_lower))

        candidates = self.concept_graph.all_tokens()
        matched_tokens: Set[str] = set()

        # Blocklist for too-generic suffixes
        ignored_suffixes = {"meta", "root", "core", "base", "type", "kind", "value"}

        for token in candidates:
            token_lower = token.lower()

            # 1. Direct full match (e.g. user typed "topic.python")
            if token_lower in query_lower:
                matched_tokens.add(token)
                continue

            # 2. Suffix match (e.g. "python" triggers "topic.programming.python")
            parts = token_lower.split(".")
            suffix = parts[-1]

            if suffix in ignored_suffixes:
                continue

            if suffix in query_words:
                matched_tokens.add(token)
                # Optimization: if suffix matches, we might want to verify context?
                # For now, aggressive recall is preferred over precision loss.

        # Deterministic synonym triggers for identity/authority questions.
        for word, tokens in self._synonym_map.items():
            if word in query_words:
                for tok in tokens:
                    if tok in candidates:
                        matched_tokens.add(tok)

        return sorted(list(matched_tokens))
