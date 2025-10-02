from __future__ import annotations

import warnings

__all__ = ["SubstringFilter", "NGramFilter"]

_DEFAULT_BANS = [
    "as an ai",
    "i'm sorry",
    "i apologize",
]


class SubstringFilter:
    def __init__(self, bans: list[str] | None = None) -> None:
        self._bans = [s.lower() for s in (bans or _DEFAULT_BANS) if s]

    def filter(self, text: str) -> str:
        s = text or ""
        low = s.lower()
        # Remove banned substrings deterministically; operate left-to-right
        for ban in self._bans:
            if not ban:
                continue
            while True:
                idx = low.find(ban)
                if idx == -1:
                    break
                # delete substring [idx:idx+len(ban)] from both cases
                end = idx + len(ban)
                s = s[:idx] + s[end:]
                low = low[:idx] + low[end:]
        # Normalize common residuals after removal
        # Collapse whitespace
        s = " ".join(s.split())
        # Remove space before punctuation
        for p in [",", ".", ";", ":"]:
            s = s.replace(f" {p}", p)
        # Remove leading punctuation and spaces deterministically
        while s and (s[0] in ",.;:- "):
            s = s[1:]
        return s


class NGramFilter(SubstringFilter):  # type: ignore[valid-type]
    """Backwards-compatible alias for SubstringFilter."""

    def __init__(self, *args, **kwargs) -> None:
        warnings.warn(
            "NGramFilter has been renamed to SubstringFilter; the alias will be "
            "removed in a future release.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)
