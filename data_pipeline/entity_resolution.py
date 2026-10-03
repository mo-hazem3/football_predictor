"""Match the same player across data sources despite different IDs and spellings.

Strategy (high precision first):
  1. Normalise names (strip accents/punctuation, lowercase, sort tokens).
  2. Block on birth year (when known) to keep comparisons cheap and safe.
  3. Score candidates with fuzzy name similarity, then use birth date and
     nationality as cross-checks: a conflict on either vetoes the match,
     agreement boosts confidence.
  4. Accept only matches above a threshold *and* clearly better than the
     runner-up (ambiguity margin), otherwise leave unmatched for review.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date

from rapidfuzz import fuzz


@dataclass(frozen=True)
class PlayerRecord:
    source: str
    source_id: str
    name: str
    birth_date: date | None = None
    nationality: str | None = None


@dataclass(frozen=True)
class Match:
    left: PlayerRecord
    right: PlayerRecord
    score: float


def normalize_name(name: str) -> str:
    """'Alejandro Grimaldo García' -> 'alejandro garcia grimaldo' (accent/order-insensitive)."""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in ascii_only.lower())
    return " ".join(sorted(cleaned.split()))


def name_similarity(a: str, b: str) -> float:
    """0-100. token_set_ratio handles missing middle/second names ('Vinicius Junior' vs 'Vinicius Jose Paixao de Oliveira Junior')."""
    na, nb = normalize_name(a), normalize_name(b)
    return max(fuzz.token_sort_ratio(na, nb), 0.9 * fuzz.token_set_ratio(na, nb))


def _score(a: PlayerRecord, b: PlayerRecord) -> float | None:
    """Combined confidence 0-100, or None if hard evidence says they differ."""
    score = name_similarity(a.name, b.name)
    if a.birth_date and b.birth_date:
        if a.birth_date != b.birth_date:
            # Strict: a different birth date is hard evidence of a different person.
            return None
        score += 10
    if a.nationality and b.nationality:
        if a.nationality.casefold() != b.nationality.casefold():
            return None
        score += 3
    return min(score, 100.0)


def resolve(
    left: list[PlayerRecord],
    right: list[PlayerRecord],
    threshold: float = 88.0,
    margin: float = 5.0,
) -> list[Match]:
    """One-to-one matching of `left` records to `right` records."""
    by_year: dict[int | None, list[PlayerRecord]] = {}
    for r in right:
        by_year.setdefault(r.birth_date.year if r.birth_date else None, []).append(r)

    proposals: list[tuple[float, PlayerRecord, PlayerRecord]] = []
    for l in left:
        pool = list(right) if l.birth_date is None else by_year.get(l.birth_date.year, []) + by_year.get(None, [])
        scored = sorted(
            ((s, r) for r in pool if (s := _score(l, r)) is not None),
            key=lambda x: -x[0],
        )
        if not scored or scored[0][0] < threshold:
            continue
        if len(scored) > 1 and scored[0][0] - scored[1][0] < margin:
            continue  # ambiguous: refuse to guess
        proposals.append((scored[0][0], l, scored[0][1]))

    # Greedy one-to-one: best scores claim their partner first.
    used_right: set[tuple[str, str]] = set()
    matches: list[Match] = []
    for score, l, r in sorted(proposals, key=lambda p: -p[0]):
        key = (r.source, r.source_id)
        if key in used_right:
            continue
        used_right.add(key)
        matches.append(Match(l, r, score))
    return matches
