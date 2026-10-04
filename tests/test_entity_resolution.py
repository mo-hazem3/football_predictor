from datetime import date

from data_pipeline.entity_resolution import PlayerRecord, name_similarity, normalize_name, resolve


def rec(src, sid, name, bd=None, nat=None):
    return PlayerRecord(src, sid, name, bd, nat)


def test_normalize_strips_accents_and_order():
    assert normalize_name("Alejandro Grimaldo García") == normalize_name("garcia, alejandro grimaldo")


def test_similarity_handles_short_vs_full_name():
    assert name_similarity("Vinicius Junior", "Vinicius Jose Paixao de Oliveira Junior") >= 85


def test_matches_across_spellings_with_birthdate():
    left = [rec("statsbomb", "1", "Mohamed Salah", date(1992, 6, 15), "Egypt")]
    right = [rec("fbref", "a", "Mohamed Salah Ghaly", date(1992, 6, 15), "Egypt")]
    out = resolve(left, right)
    assert len(out) == 1 and out[0].right.source_id == "a"


def test_birthdate_conflict_vetoes_identical_names():
    left = [rec("statsbomb", "1", "Carlos Silva", date(1999, 1, 1))]
    right = [rec("fbref", "a", "Carlos Silva", date(2001, 5, 5))]
    assert resolve(left, right) == []


def test_nationality_conflict_vetoes():
    left = [rec("statsbomb", "1", "Daniel Martin", None, "Spain")]
    right = [rec("fbref", "a", "Daniel Martin", None, "England")]
    assert resolve(left, right) == []


def test_ambiguous_candidates_are_left_unmatched():
    left = [rec("statsbomb", "1", "Luis Garcia")]
    right = [rec("fbref", "a", "Luis Garcia"), rec("fbref", "b", "Luis Garcia")]
    assert resolve(left, right) == []


def test_one_to_one_assignment():
    left = [rec("s", "1", "Karim Benzema", date(1987, 12, 19)), rec("s", "2", "Karim Benzema", date(1987, 12, 19))]
    right = [rec("f", "a", "Karim Benzema", date(1987, 12, 19))]
    # Two identical left records compete for one right record -> at most one match
    assert len(resolve(left, right)) <= 1


# ---- club-aware second pass --------------------------------------------------

from data_pipeline.entity_resolution import Match, learn_club_map, resolve_within_clubs


def _p(src, i, name, *clubs):
    return PlayerRecord(src, str(i), name, clubs=frozenset(clubs))


def test_learn_club_map_needs_support_and_dominant_partner():
    ms = [Match(_p("u", i, "a", "RB Leipzig"), _p("t", i, "a", "RasenBallsport Leipzig"), 100) for i in range(3)]
    ms += [Match(_p("u", 9, "x", "Hoffenheim"), _p("t", 9, "x", "TSG 1899 Hoffenheim"), 100)]  # support 1 < 3
    assert learn_club_map(ms) == {"RB Leipzig": "RasenBallsport Leipzig"}


def test_club_pass_resolves_nickname_inside_mapped_club_only():
    cmap = {"Leverkusen": "Bayer 04 Leverkusen"}
    left = [_p("u", 1, "Alex Grimaldo", "Leverkusen")]
    right = [
        _p("t", 1, "Alejandro Grimaldo", "Bayer 04 Leverkusen"),
        _p("t", 2, "Alejandro Garnacho", "Manchester United"),
    ]
    assert [m.right.source_id for m in resolve_within_clubs(left, right, cmap)] == ["1"]
    # same nickname but the real player is at another club: must not match
    assert resolve_within_clubs(left, right[1:], cmap) == []


def test_club_pass_requires_shared_token_and_clear_winner():
    cmap = {"A": "A FC"}
    assert resolve_within_clubs([_p("u", 1, "Julian Chabot", "A")], [_p("t", 1, "Jeff Schabot", "A FC")], cmap) == []
    twins = [_p("t", 1, "Gabriel Paulista", "A FC"), _p("t", 2, "Gabriel Magalhaes", "A FC")]
    assert resolve_within_clubs([_p("u", 1, "Gabriel", "A")], twins, cmap) == []  # ambiguous -> refuse


# ---- birth year only (FBref) -------------------------------------------------

def test_birth_year_vetoes_and_boosts_when_no_full_date():
    a = PlayerRecord("fbref", "1", "Jamal Musiala", birth_year=2003)
    full = PlayerRecord("tm", "1", "Jamal Musiala", date(2003, 2, 26))
    other_year = PlayerRecord("tm", "2", "Jamal Musiala", date(2004, 2, 26))
    assert resolve([a], [other_year]) == []
    m = resolve([a], [full, other_year])
    assert [x.right.source_id for x in m] == ["1"]


def test_full_dates_still_take_precedence_over_year():
    a = PlayerRecord("x", "1", "Same Name", date(2000, 5, 1))
    b = PlayerRecord("y", "1", "Same Name", date(2000, 6, 1), birth_year=2000)
    assert resolve([a], [b]) == []  # same year, different full date -> different person
