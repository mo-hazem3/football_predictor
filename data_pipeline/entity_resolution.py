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
    clubs: frozenset[str] = frozenset()  # clubs played for in the block (league-season); source-specific spelling
    birth_year: int | None = None  # for sources that only publish the year (FBref)

    @property
    def year(self) -> int | None:
        return self.birth_date.year if self.birth_date else self.birth_year


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
    elif a.year and b.year:
        # Only a year is known on at least one side: a different year still vetoes, agreement is weaker evidence.
        if a.year != b.year:
            return None
        score += 5
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
        by_year.setdefault(r.year, []).append(r)

    proposals: list[tuple[float, PlayerRecord, PlayerRecord]] = []
    for l in left:
        pool = list(right) if l.year is None else by_year.get(l.year, []) + by_year.get(None, [])
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


# ---------------------------------------------------------------- club-aware second pass
#
# Name-only matching cannot resolve nicknames ('Alex Grimaldo' vs 'Alejandro
# Grimaldo'). Club is strong evidence, but the two sources spell clubs
# differently and we do not want a hand-written alias table. So: learn the
# club mapping from the unambiguous name matches, then use it to resolve what
# is left inside each club, where the candidate pool is only a handful of players.


def learn_club_map(matches: list[Match], min_support: int = 3, min_share: float = 0.6) -> dict[str, str]:
    """Left-club -> right-club, by co-occurrence among confident matches.

    A pair is kept only when the right club accounts for at least `min_share`
    of that left club's matched players and has `min_support` of them.
    """
    counts: dict[str, dict[str, int]] = {}
    for m in matches:
        for lc in m.left.clubs:
            for rc in m.right.clubs:
                counts.setdefault(lc, {}).setdefault(rc, 0)
                counts[lc][rc] += 1
    club_map = {}
    for lc, rcs in counts.items():
        rc, n = max(rcs.items(), key=lambda kv: kv[1])
        if n >= min_support and n / sum(rcs.values()) >= min_share:
            club_map[lc] = rc
    return club_map


def resolve_within_clubs(
    left: list[PlayerRecord],
    right: list[PlayerRecord],
    club_map: dict[str, str],
    threshold: float = 70.0,
    margin: float = 10.0,
) -> list[Match]:
    """Match leftover players inside their (mapped) club, with a relaxed name threshold.

    Safety nets compensate for the lower threshold: candidates must come from
    the player's own club, must share at least one exact name token (usually
    the surname), and must beat the runner-up by `margin`.
    """
    by_club: dict[str, list[PlayerRecord]] = {}
    for r in right:
        for c in r.clubs:
            by_club.setdefault(c, []).append(r)

    proposals: list[tuple[float, PlayerRecord, PlayerRecord]] = []
    for l in left:
        pool = {id(r): r for lc in l.clubs if (rc := club_map.get(lc)) for r in by_club.get(rc, [])}
        l_tokens = set(normalize_name(l.name).split())
        scored = sorted(
            ((s, r) for r in pool.values()
             if l_tokens & set(normalize_name(r.name).split()) and (s := _score(l, r)) is not None),
            key=lambda x: -x[0],
        )
        if not scored or scored[0][0] < threshold:
            continue
        if len(scored) > 1 and scored[0][0] - scored[1][0] < margin:
            continue
        proposals.append((scored[0][0], l, scored[0][1]))

    used: set[tuple[str, str]] = set()
    matches = []
    for score, l, r in sorted(proposals, key=lambda p: -p[0]):
        if (r.source, r.source_id) not in used:
            used.add((r.source, r.source_id))
            matches.append(Match(l, r, score))
    return matches
