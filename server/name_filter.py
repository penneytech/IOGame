"""Profanity filter for player-supplied names.

Implementation notes
--------------------
We deliberately do not embed any blocklist in this repository's source.
All flagged terms come from the third-party ``better_profanity`` package's
own data file (shipped inside its installed package directory) and from
its public ``contains_profanity`` API. Students who browse this repo
will not see any offensive words in plain text.

Detection works in two passes:

1. ``profanity.contains_profanity`` for whole-word / token matches.
2. A substring scan against the package's wordlist (restricted to terms
   of length >= 4 to avoid false positives like "ass" matching "class"
   or "assassin"). The input is first normalised by lowercasing,
   collapsing common leetspeak (``@``->``a``, ``0``->``o``, ``1``->``i``,
   ``3``->``e``, ``4``->``a``, ``5``->``s``, ``7``->``t``, ``$``->``s``,
   ``!``->``i``), stripping non-letters, and collapsing repeated letters
   (``shiiit`` -> ``shit``).

This is best-effort: a determined attacker can always find a way around
a profanity filter. The goal is to stop casual abuse, not to be perfect.
"""

from __future__ import annotations

import os
import re
from typing import Iterable

from better_profanity import profanity

profanity.load_censor_words()


def _load_wordlist() -> list[str]:
    """Read the library's bundled wordlist from disk."""
    import better_profanity as _pkg

    path = os.path.join(os.path.dirname(_pkg.__file__), "profanity_wordlist.txt")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return [w.strip().lower() for w in fh if w.strip()]
    except OSError:
        return []


_WORDS: list[str] = [w for w in _load_wordlist() if len(w) >= 4]

_LEET = str.maketrans({
    "@": "a", "4": "a",
    "$": "s", "5": "s",
    "0": "o",
    "1": "i", "!": "i", "|": "i",
    "3": "e",
    "7": "t",
    "9": "g",
    "8": "b",
})

_NON_ALPHA = re.compile(r"[^a-z]+")
_REPEAT = re.compile(r"(.)\1{2,}")


def _normalise(name: str) -> str:
    s = name.lower().translate(_LEET)
    s = _NON_ALPHA.sub("", s)
    # Collapse runs of 3+ identical letters down to one (shiiit -> shit).
    s = _REPEAT.sub(r"\1", s)
    return s


def is_offensive(name: str) -> bool:
    """Return True if ``name`` appears to contain a blocked term."""
    if not name:
        return False
    if profanity.contains_profanity(name):
        return True
    n = _normalise(name)
    if not n:
        return False
    for w in _WORDS:
        if w in n:
            return True
    return False


def check_name(name: str) -> str:
    """Validator entry point. Returns the original name or raises ValueError."""
    if is_offensive(name):
        raise ValueError("name not allowed; please pick something else")
    return name


__all__ = ["is_offensive", "check_name"]
