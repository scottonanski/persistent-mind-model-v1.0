from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from pmm.runtime.embeddings import compute_embedding, cosine_similarity

_TARGET_PHRASES = (
    "personal ontology",
    "identity evolution",
    "autonomy reflection",
    "emergent self",
    "metaphor for becoming",
    "self concept",
)

_CONTEXT_BOOST_PHRASES = {
    "ontology",
    "autonomy",
    "identity",
    "emergent",
    "metaphor",
    "worldview",
    "becoming",
}


@dataclass
class GraphInsightTrigger:
    """Semantic detector for turns that warrant graph evidence injection."""

    threshold: float = 0.33
    context_threshold: float = 0.28
    _target_vectors: dict[str, list[float]] = field(default_factory=dict)

    def _embed(self, text: str) -> list[float] | None:
        try:
            vec = compute_embedding(text)
            if isinstance(vec, list) and vec:
                return vec
        except Exception:
            return None
        return None

    def _target_vector(self, phrase: str) -> list[float] | None:
        if phrase in self._target_vectors:
            return self._target_vectors[phrase]
        vec = self._embed(phrase)
        if vec is not None:
            self._target_vectors[phrase] = vec
        return vec

    def should_inject(
        self,
        user_text: str,
        context_lines: Iterable[str] | None = None,
    ) -> bool:
        payload = (user_text or "").strip()
        if not payload:
            return False

        vec = self._embed(payload)
        if vec is None:
            return False

        for phrase in _TARGET_PHRASES:
            target_vec = self._target_vector(phrase)
            if not target_vec:
                continue
            sim = cosine_similarity(vec, target_vec)
            if sim >= self.threshold:
                return True

        if context_lines:
            context_text = " ".join(str(line) for line in context_lines if line)
            context_text = context_text.strip()
            if context_text:
                ctx_vec = self._embed(context_text)
                if ctx_vec:
                    for phrase in _TARGET_PHRASES:
                        tvec = self._target_vector(phrase)
                        if not tvec:
                            continue
                        sim = cosine_similarity(ctx_vec, tvec)
                        if sim >= self.context_threshold:
                            return True

        lowered = payload.lower()
        if any(kw in lowered for kw in _CONTEXT_BOOST_PHRASES):
            return True

        return False
