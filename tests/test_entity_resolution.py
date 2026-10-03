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
