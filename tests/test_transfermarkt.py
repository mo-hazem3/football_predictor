from data_pipeline.cache import _cache_path
from data_pipeline.sources.transfermarkt import (
    parse_clubs, parse_market_values, parse_money, parse_squad, parse_transfers,
)
from pathlib import Path

CLUBS_HTML = """
<table class="items"><tbody>
<tr><td class="hauptlink no-border-links"><a href="/manchester-city/startseite/verein/281/saison_id/2023">Manchester City</a></td>
    <td><a href="/manchester-city/kader/verein/281/saison_id/2023">36</a></td></tr>
<tr><td class="hauptlink no-border-links"><a href="/fc-arsenal/startseite/verein/11/saison_id/2023">Arsenal FC</a></td></tr>
</tbody></table>"""

SQUAD_HTML = """
<table class="items"><thead><tr><th>#</th><th>Player</th></tr></thead><tbody>
<tr class="odd">
  <td class="zentriert rueckennummer"><div class="rn_nummer">1</div></td>
  <td class="posrela"><table class="inline-table">
    <tr><td rowspan="2"><img alt="x"></td><td class="hauptlink"><a href="/lukas-hradecky/profil/spieler/48015">Lukas Hradecky</a></td></tr>
    <tr><td>Goalkeeper</td></tr></table></td>
  <td class="zentriert">24/11/1989 (34)</td>
  <td class="zentriert"><img class="flaggenrahmen" title="Finland"><img class="flaggenrahmen" title="Slovakia"></td>
  <td class="zentriert">1,92m</td>
  <td class="zentriert">right</td>
  <td class="zentriert">01/07/2020</td>
  <td class="rechts hauptlink"><a href="/x">€2.50m</a></td>
</tr>
<tr class="even">
  <td class="zentriert rueckennummer"><div class="rn_nummer">99</div></td>
  <td class="posrela"><table class="inline-table">
    <tr><td class="hauptlink"><a href="/kid/profil/spieler/7">Young Kid</a></td></tr>
    <tr><td>Centre-Forward</td></tr></table></td>
  <td class="zentriert">-</td>
  <td class="zentriert"><img class="flaggenrahmen" title="Egypt"></td>
  <td class="zentriert">-</td>
  <td class="zentriert"></td>
  <td class="rechts hauptlink">-</td>
</tr>
</tbody></table>"""

CLUB = {"club_id": 15, "name": "Bayer 04 Leverkusen"}


def test_parse_money():
    assert parse_money("€40.63m") == 40_630_000
    assert parse_money("€500k") == 500_000
    assert parse_money("€1.46bn") == 1_460_000_000
    assert parse_money("-") is None and parse_money("?") is None and parse_money(None) is None


def test_parse_clubs():
    assert parse_clubs(CLUBS_HTML) == [
        {"club_id": 281, "slug": "manchester-city", "name": "Manchester City"},
        {"club_id": 11, "slug": "fc-arsenal", "name": "Arsenal FC"},
    ]


def test_parse_squad_extracts_bio_and_handles_missing_fields():
    full, sparse = parse_squad(SQUAD_HTML, CLUB, 2023, "Bundesliga")
    assert full["tm_player_id"] == 48015 and full["position"] == "Goalkeeper"
    assert full["birth_date"] == "1989-11-24" and full["height_cm"] == 192 and full["foot"] == "right"
    assert full["nationality"] == "Finland" and full["nationalities"] == "Finland|Slovakia"
    assert full["market_value_eur"] == 2_500_000
    # the joined date must not be mistaken for a birth date
    assert sparse["birth_date"] is None and sparse["height_cm"] is None and sparse["foot"] is None
    assert sparse["market_value_eur"] is None and sparse["nationality"] == "Egypt"


def test_parse_market_values():
    payload = {"list": [
        {"y": 1_000_000, "datum_mw": "01/07/2020", "verein": "Bayern Munich", "age": "17"},
        {"y": None, "datum_mw": "bad"},
    ]}
    assert parse_market_values(payload, 580195) == [
        {"tm_player_id": 580195, "date": "2020-07-01", "value_eur": 1_000_000, "club": "Bayern Munich", "age": 17}
    ]


def _transfer(tid, fee, future=0):
    return {
        "url": f"/p/transfers/spieler/1/transfer_id/{tid}", "futureTransfer": future,
        "dateUnformatted": "2020-07-01", "season": "20/21", "marketValue": "€1.00m", "fee": fee,
        "from": {"clubName": "FC Bayern U19", "href": "/fc-bayern-u19/transfers/verein/1462/saison_id/2020"},
        "to": {"clubName": "Bayern Munich", "href": "/bayern-munich/transfers/verein/27/saison_id/2020"},
    }


def test_parse_transfers_keeps_youth_moves_and_separates_fee_kinds():
    rows = parse_transfers({"transfers": [_transfer(1, "€15.00m"), _transfer(2, "Loan fee:€500k"), _transfer(3, "-"), _transfer(4, "€1m", future=1)]}, 1)
    assert [r["transfer_id"] for r in rows] == [1, 2, 3]  # future transfers dropped
    assert rows[0]["fee_eur"] == 15_000_000 and rows[0]["from_club_id"] == 1462 and rows[0]["to_club_id"] == 27
    assert rows[1]["fee_eur"] is None and rows[1]["fee_text"] == "Loan fee:€500k"
    assert rows[2]["fee_eur"] is None


def test_cache_path_is_a_valid_filename_for_query_urls():
    p = _cache_path("https://x.com/a/plus/?saison_id=2023", Path("c"), suffix="html")
    assert "?" not in p.name and "=" not in p.name and p.suffix == ".html"
