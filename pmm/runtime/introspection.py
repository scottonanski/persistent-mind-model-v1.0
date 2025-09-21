from __future__ import annotations

from typing import Dict, List, Tuple
from dataclasses import dataclass
from typing import Callable, Protocol, Any

from pmm.runtime.embeddings import compute_embedding, cosine_similarity, digest_vector


COMPLETION_EXEMPLARS: Dict[str, List[str]] = {
    "complete": [
        "I have finished this reflection",
        "this task is now complete",
        "I have resolved the issue",
        "I reached a clear conclusion",
    ],
    "incomplete": [
        "I still need to think about this",
        "this is ongoing",
        "I don't have an answer yet",
        "work in progress",
    ],
}

COMPLETION_THRESHOLD = 0.65


def _embedding(text: str) -> List[float]:
    vec = compute_embedding(text or "")
    return vec if isinstance(vec, list) else []


def _prepare_samples(
    exemplars: Dict[str, List[str]],
) -> Dict[str, List[Dict[str, Any]]]:
    samples: Dict[str, List[Dict[str, Any]]] = {}
    for label, texts in exemplars.items():
        vectors = []
        for text in texts:
            vec = _embedding(text)
            if vec:
                vectors.append({"text": text, "vector": vec})
        samples[label] = vectors
    return samples


COMPLETION_SAMPLES = _prepare_samples(COMPLETION_EXEMPLARS)


def _centroid(vectors: List[List[float]]) -> List[float]:
    if not vectors:
        return []
    length = len(vectors[0])
    summed = [0.0] * length
    for vec in vectors:
        for idx, value in enumerate(vec):
            summed[idx] += float(value)
    count = float(len(vectors)) or 1.0
    return [value / count for value in summed]


COMPLETION_CENTROIDS: Dict[str, List[float]] = {
    label: _centroid([sample["vector"] for sample in samples])
    for label, samples in COMPLETION_SAMPLES.items()
    if samples
}


def detect_reflection_completion(
    text: str, threshold: float = COMPLETION_THRESHOLD
) -> Dict[str, Any]:
    """Return semantic completion status for a reflection."""
    if not isinstance(text, str) or not text.strip():
        return {
            "status": "incomplete",
            "score": 0.0,
            "threshold": threshold,
            "exemplar": "",
            "embedding_digest": "",
        }

    vec = _embedding(text)
    digest = digest_vector(vec) if vec else ""

    complete_samples = COMPLETION_SAMPLES.get("complete", [])
    incomplete_samples = COMPLETION_SAMPLES.get("incomplete", [])

    complete_best = 0.0
    complete_exemplar = ""
    for sample in complete_samples:
        score = float(cosine_similarity(vec, sample["vector"]))
        if score > complete_best:
            complete_best = score
            complete_exemplar = sample["text"]

    incomplete_best = 0.0
    for sample in incomplete_samples:
        score = float(cosine_similarity(vec, sample["vector"]))
        if score > incomplete_best:
            incomplete_best = score

    complete_centroid = COMPLETION_CENTROIDS.get("complete", [])
    incomplete_centroid = COMPLETION_CENTROIDS.get("incomplete", [])

    if complete_centroid:
        complete_centroid_score = float(cosine_similarity(vec, complete_centroid))
        complete_best = max(complete_best, complete_centroid_score)
    if incomplete_centroid:
        incomplete_centroid_score = float(cosine_similarity(vec, incomplete_centroid))
        incomplete_best = max(incomplete_best, incomplete_centroid_score)

    if complete_best >= threshold and complete_best >= incomplete_best:
        return {
            "status": "complete",
            "score": complete_best,
            "threshold": threshold,
            "exemplar": complete_exemplar,
            "embedding_digest": digest,
        }

    if incomplete_best >= threshold:
        return {
            "status": "incomplete",
            "score": incomplete_best,
            "threshold": threshold,
            "exemplar": "",
            "embedding_digest": digest,
        }

    return {
        "status": "incomplete",
        "score": 0.0,
        "threshold": threshold,
        "exemplar": "",
        "embedding_digest": digest,
    }


# Deterministic, append-only audit that inspects recent events and proposes
# annotation-only audit_report events. No mutations, no hidden state.
#
# Event shape expected from EventLog.read_all():
# {"id": int, "ts": str, "kind": str, "content": str, "meta": dict}


def run_audit(events: List[Dict], window: int = 50) -> List[Dict]:
    """Return a list of audit_report dicts for recent events.

    Deterministic rules over the last `window` events:
    - closure-audit: commitment_close without a prior evidence_candidate after its last open
    - duplicate-close: same cid closed twice without a re-open in between
    - orphan-evidence: evidence_candidate without a corresponding commitment_close in the window
    - fact-check: reflection asserts completion but relevant commitment still open and no close

    Notes
    -----
    - Pure function: no external I/O; caller is responsible for appending results.
    - All produced audit_report.meta.target_eids will reference prior event ids by construction.
    """
    if not events:
        return []

    # Consider only the trailing window for auditing
    tail = events[-int(window) :] if window and window > 0 else events[:]

    # Build maps for quick lookups within the window
    opens_by_cid: Dict[str, List[int]] = {}
    closes_by_cid: Dict[str, List[int]] = {}
    cands_by_cid: Dict[str, List[int]] = {}

    for ev in tail:
        k = ev.get("kind")
        m = ev.get("meta") or {}
        cid = str(m.get("cid") or "")
        if k == "commitment_open" and cid:
            opens_by_cid.setdefault(cid, []).append(int(ev.get("id") or 0))
        elif k == "commitment_close" and cid:
            closes_by_cid.setdefault(cid, []).append(int(ev.get("id") or 0))
        elif k == "evidence_candidate" and cid:
            cands_by_cid.setdefault(cid, []).append(int(ev.get("id") or 0))

    audits: List[Dict] = []

    # Helper to construct an audit_report dict with content trim and bounds
    def _audit(content: str, targets: List[int], category: str) -> None:
        # Ensure targets are valid prior ids and unique/sorted
        prior_ids = sorted({int(t) for t in targets if int(t) > 0})
        # Content bound: <=500 chars
        msg = (content or "")[:500]
        audits.append(
            {
                "kind": "audit_report",
                "content": msg,
                "meta": {"target_eids": prior_ids, "category": category},
            }
        )

    # --- Rule: closure-audit ---
    for ev in tail:
        if ev.get("kind") != "commitment_close":
            continue
        m = ev.get("meta") or {}
        cid = str(m.get("cid") or "")
        close_id = int(ev.get("id") or 0)
        if not cid or close_id <= 0:
            continue
        # Find the last open before this close in tail (if any)
        last_open = 0
        for oid in opens_by_cid.get(cid, []):
            if oid < close_id and oid > last_open:
                last_open = oid
        # Check for any candidate after last_open and <= close_id
        ok = any(last_open < x <= close_id for x in cands_by_cid.get(cid, []))
        if not ok:
            targets = [t for t in [last_open, close_id] if t > 0]
            _audit(
                "Commitment close lacked evidence_candidate",
                targets,
                "closure-audit",
            )

    # --- Rule: duplicate-close ---
    for cid, closes in closes_by_cid.items():
        # Consider sequence of closes after last open in the window
        last_open = 0
        for oid in opens_by_cid.get(cid, []):
            if oid > last_open:
                last_open = oid
        # Filter closes strictly after last_open
        seq = [c for c in closes if c > last_open]
        if len(seq) >= 2:
            # Flag the second (and any subsequent) close as duplicate-close
            for dup_id in seq[1:]:
                _audit(
                    "Duplicate commitment_close without re-open",
                    [last_open, seq[0], dup_id],
                    "duplicate-close",
                )

    # --- Rule: orphan-evidence ---
    for cid, cand_ids in cands_by_cid.items():
        # For each candidate, if no close for this cid appears in the tail after it, flag
        closes_sorted = sorted(closes_by_cid.get(cid, []))
        for cand_id in cand_ids:
            has_close_after = any(cl > cand_id for cl in closes_sorted)
            if not has_close_after:
                _audit(
                    "Evidence candidate has no corresponding close in window",
                    [cand_id],
                    "orphan-evidence",
                )

    # --- Rule: reflection fact-check ---
    # Semantic completion detection combined with simple token overlap against open commitments
    def _tokens(s: str) -> List[str]:
        import re as _re

        s2 = _re.sub(r"[^a-z0-9]+", " ", (s or "").lower())
        toks = [t for t in s2.split() if t]
        return toks

    # Build a quick map of open commitments at any point (approximate within window):
    # For fact-check, we need opens that are not followed by a close for the same cid within the tail.
    open_like: Dict[str, Tuple[int, str]] = {}  # cid -> (last_open_id, text)
    for ev in tail:
        if ev.get("kind") == "commitment_open":
            m = ev.get("meta") or {}
            cid = str(m.get("cid") or "")
            txt = str(m.get("text") or "")
            if cid:
                open_like[cid] = (int(ev.get("id") or 0), txt)
        elif ev.get("kind") == "commitment_close":
            m = ev.get("meta") or {}
            cid = str(m.get("cid") or "")
            if cid in open_like:
                # Closed now → remove from open_like
                open_like.pop(cid, None)

    # For each reflection in tail, if semantic completion is detected and it overlaps with any
    # still-open commitment text, and there's no close for that cid after the reflection, flag.
    for ev in tail:
        if ev.get("kind") != "reflection":
            continue
        rid = int(ev.get("id") or 0)
        text = ev.get("content") or ""
        completion_analysis = detect_reflection_completion(text)
        if completion_analysis["status"] != "complete":
            continue
        rtoks = set(_tokens(text))
        # Try to match a cid by simple token overlap with the open commitment text
        for cid, (oid, ctxt) in open_like.items():
            # Only consider commitments whose open is prior to the reflection
            if int(oid) >= rid:
                continue
            ctoks = set(_tokens(ctxt))
            if not ctoks:
                continue
            overlap = rtoks.intersection(ctoks)
            if not overlap:
                continue
            # Is there a close for this cid after the reflection within tail?
            closes_after = [cl for cl in closes_by_cid.get(cid, []) if cl > rid]
            if not closes_after:
                _audit(
                    f"Reflection marked complete (score {completion_analysis['score']:.3f}) but commitment still open",
                    [rid, oid],
                    "fact-check",
                )
                # One audit per reflection per cid match is sufficient; continue to next cid
    # --- Rule: novelty_trend over recent reflections (deterministic) ---
    try:
        # Collect last M reflections across the available window
        M = 10
        R = 3  # recent pairs
        P = 3  # prior pairs
        refs_all = [ev for ev in events if ev.get("kind") == "reflection"]
        if len(refs_all) >= 3:
            refs_tail = refs_all[-M:]

            def _tokset(s: str) -> set:
                s2 = (s or "").lower()
                import re as _re

                s2 = _re.sub(r"[^a-z0-9]+", " ", s2)
                toks = [t for t in s2.split() if len(t) > 2]
                return set(toks)

            # Adjacent-pair Jaccard similarities with event ids
            pairs: List[Tuple[Tuple[int, int], float]] = []
            for i in range(1, len(refs_tail)):
                a = refs_tail[i - 1]
                b = refs_tail[i]
                A = _tokset(a.get("content") or "")
                B = _tokset(b.get("content") or "")
                if not A and not B:
                    j = 1.0
                else:
                    denom = len(A.union(B)) or 1
                    j = float(len(A.intersection(B))) / float(denom)
                pairs.append(((int(a.get("id") or 0), int(b.get("id") or 0)), j))

            # Compute recent/prior means (handle short tails)
            n_pairs = len(pairs)
            if n_pairs >= 1:
                r_n = min(R, n_pairs)
                recent_vals = [pairs[-k][1] for k in range(1, r_n + 1)]
                prior_count = min(P, max(0, n_pairs - r_n))
                prior_vals = (
                    [pairs[-(r_n + k)][1] for k in range(1, prior_count + 1)]
                    if prior_count > 0
                    else []
                )
                import statistics as _stats

                dup_recent = float(_stats.mean(recent_vals)) if recent_vals else 0.0
                dup_prior = float(_stats.mean(prior_vals)) if prior_vals else dup_recent
                delta = dup_recent - dup_prior
                if delta >= 0.10:
                    trend = "falling"  # novelty worse (dup ↑)
                elif delta <= -0.10:
                    trend = "rising"  # novelty better (dup ↓)
                else:
                    trend = "same"

                # Top pairs by similarity (highest duplication) for quick inspection
                pairs_sorted = sorted(pairs, key=lambda t: float(t[1]), reverse=True)
                top_pairs = [
                    [int(a), int(b), float(sc)] for (a, b), sc in pairs_sorted[:3]
                ]

                audits.append(
                    {
                        "kind": "audit_report",
                        "content": "",
                        "meta": {
                            "category": "novelty_trend",
                            "value": trend,
                            "stats": {
                                "recent": float(dup_recent),
                                "prior": float(dup_prior),
                                "window": int(M),
                                "recent_pairs": int(r_n),
                                "prior_pairs": int(prior_count),
                            },
                            "top_pairs": top_pairs,
                            # Keep target_eids empty for this category; not bound to specific prior ids
                            "target_eids": [],
                        },
                    }
                )
    except Exception:
        # Never let novelty audit break other audits
        pass

    return audits


# ---------------- Log-only introspection (prompted summary) -----------------


class LLMCall(Protocol):
    def __call__(self, prompt: str) -> str: ...


_INTROSPECTION_PROMPT_TEMPLATE = (
    "[INTROSPECTION]\n"
    "Topic: {topic}\n"
    "Scope: {scope}\n"
    "Task: Provide a concise, factual summary based only on the PMM code, events, and projections.\n"
    "Rules:\n"
    "  - Do not propose actions.\n"
    "  - Do not open/close commitments.\n"
    "  - Do not modify identity/traits.\n"
    "  - Output a short paragraph; no lists.\n"
)


def build_prompt(topic: str, scope: str) -> str:
    return _INTROSPECTION_PROMPT_TEMPLATE.format(
        topic=str(topic).strip(), scope=str(scope).strip()
    )


@dataclass(frozen=True)
class IntrospectionResult:
    prompt: str
    summary: str


def run_introspection(
    *,
    topic: str,
    scope: str,
    llm: LLMCall,
    append_event: Callable[[Dict[str, Any]], Any],
) -> IntrospectionResult:
    """
    Log-only introspection:
      - Builds a deterministic prompt
      - Calls LLM (injected)
      - Appends an `introspection_report` event with {topic, scope, summary}
      - Returns the prompt + summary for inspection
    No side effects beyond the single event append.
    """
    prompt = build_prompt(topic, scope)
    summary = llm(prompt)

    append_event(
        {
            "kind": "introspection_report",
            "payload": {"topic": topic, "scope": scope, "summary": summary},
        }
    )

    return IntrospectionResult(prompt=prompt, summary=summary)
