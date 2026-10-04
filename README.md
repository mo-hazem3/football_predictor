# Football player comps & trajectory projection

Finds statistically similar football players (controlling for age, league quality and position) and projects likely career trajectories as **probability ranges** based on what comparable historical players became. Portfolio project; see `football-project-brief.md` for full scope.

> Status: **Phase 1 in progress** — data pipeline & entity resolution.

## Layout

| Path | Purpose |
|---|---|
| `data_pipeline/` | scraping/ingestion, caching, entity resolution (framework-agnostic) |
| `features/` | percentile ranks, league adjustment (planned) |
| `ml/` | similarity engine, trajectory model, backtest (planned) |
| `backend/` | Django + DRF (planned) |
| `frontend/` | React + TypeScript (planned) |

## Quick start

```bash
pip install -e ".[dev]"
python -m data_pipeline.ingest_statsbomb --list
python -m data_pipeline.ingest_statsbomb --competition 9 --season 281   # Bundesliga 2023/24
python -m data_pipeline.ingest_understat --seasons 2014 2025            # all five leagues
python -m data_pipeline.ingest_transfermarkt --seasons 2014 2025        # squads: birth date, nationality, value (~1h, 3s/request)
python -m data_pipeline.ingest_transfermarkt --history --history-limit 500   # per-player value + transfer history, resumable
python -m data_pipeline.link_understat_tm                               # Understat id -> Transfermarkt id
python -m data_pipeline.ingest_fbref --seasons 2014 2025                # FBref via soccerdata (~1 h, opens Chrome)
python -m data_pipeline.link_fbref_tm                                   # FBref -> Transfermarkt
python -m features.build                                                # age, per-90, league adjustment, percentiles
python -m ml.comps "Lamine Yamal" --season 2024                         # closest comparable players + gap analysis
python -m ml.evaluate_similarity                                        # label-free metric check
python -m ml.visualize                                                  # PCA sanity figure -> docs/comps_pca.png
python -m ml.project "Lamine Yamal" --season 2024                       # forecast: probabilities + value range + comps as evidence
python -m ml.backtest --out docs/backtest_h3.txt --calibration-out docs/elite_calibration.json   # rolling-origin backtest (~6 min)
pytest
```

Downloads are cached under `data/cache/` (never re-fetched) and requests are rate-limited. Output lands in `data/db/football.sqlite`.

## Data caveats

StatsBomb open data covers only selected competitions/seasons (e.g. only Bayer Leverkusen for Bundesliga 2023/24), so it is the event-level source, not the backbone for career histories. Understat (xG/xA, 2014–2025, top-5 leagues) is the breadth source. It is fetched with plain `requests` through the shared cache rather than `soccerdata`, whose TLS client ignores HTTP proxies.

Transfermarkt provides what the stat sources lack: birth date, nationality(ies), position, height, season-end market value (squad pages) and, per player, market-value history and full transfer history including youth/reserve moves (the pathway signal for the similarity engine). Squad pages are HTML; history comes from the site's own JSON endpoints. Requests go through the shared cache at 3 s intervals with an honest User-Agent.

FBref works through `soccerdata` on a normal machine: it drives its own automated Chrome via seleniumbase (a window will appear and navigate; your normal browser is unaffected, but leave that window alone while it runs). `soccerdata` keeps its own cache in `~/soccerdata/`, outside `data/cache/`. FBref has withdrawn its Opta-based advanced tables, so only `standard`, `misc` and `keeper` are available: minutes, goals/assists, cards, tackles won, interceptions, crosses, fouls, nationality, birth year, and goalkeeper saves/shots-on-target-against/clean sheets. No xG, passing or pressure data comes from FBref. Tackle and interception definitions appear to change between 2017 and 2023 (the tackle/interception ratio flips), so they are ranked within season and never compared raw across seasons. Ingested integrity check: FBref's total minutes per league-season are within 0.4% of Understat's for all 60 league-seasons, so no page was truncated.

## Entity resolution

Understat has no birth dates or nationalities, so linking it to Transfermarkt rests on names plus club context, in two passes (`data_pipeline/entity_resolution.py`, `link_understat_tm.py`):

1. **Name pass** — accent/order-insensitive fuzzy match over one record per Transfermarkt player (a mid-season mover appears in two squads; without deduplication identical names tie and are rejected as ambiguous). Accept only above a threshold *and* clearly ahead of the runner-up.
2. **Club pass** — the Understat-club to Transfermarkt-club mapping is *learned* from the name-pass matches (no hand-written alias table), then leftovers are matched inside their club with a relaxed threshold, requiring a shared name token and a clear winner. This resolves nicknames (`Alex Grimaldo` / `Alejandro Grimaldo`, `Danny` / `Daniel Drinkwater`).

FBref is linked to Transfermarkt the same way (`link_fbref_tm.py`) but has no player id and only a birth *year*, which acts as a hard veto (`PlayerRecord.birth_year`). Coverage is reported weighted by minutes played, since missing a bench player matters far less than missing a starter. Understat results over all 60 league-seasons (2014–2025, top-5 leagues), share of Understat minutes linked to a Transfermarkt player:

| League | Name pass (min–max of seasons) | After club pass (min–max) | Players linked via club pass |
|---|---|---|---|
| Bundesliga | 97.8–99.9% | 98.7–100.0% | 32 of 5813 |
| EPL | 97.6–99.1% | 99.4–100.0% | 112 of 6424 |
| La_liga | 92.3–95.4% | 97.6–99.3% | 338 of 6792 |
| Ligue_1 | 96.7–99.4% | 97.9–100.0% | 101 of 6658 |
| Serie_A | 96.8–99.0% | 98.9–99.7% | 76 of 6887 |

The club pass matters most in La Liga (~93% -> ~98%), where compound and accented names defeat the name pass. Precision is checked by consistency: an Understat id must map to the same Transfermarkt id in every season. Only 17 of 9,434 players (0.18%) violated that, all mononyms (Juanfran, Mariano, Emerson, Toño) that a name cannot separate; those links are dropped rather than guessed (`drop_conflicts`). Final table: 9,410 players, 32,206 player-seasons, strictly one-to-one. A manual read of the first 24 club-pass matches found no errors.

FBref coverage is 98.2–100% of minutes in every league (club pass: 269 of ~32,500 players). Because Understat and FBref are linked to Transfermarkt independently, with different evidence, they give a label-free precision check: for the 32,020 player-seasons linked by both, 32,004 (99.95%) agree on minutes played to within 10% / 90 minutes, whereas a wrong link in either source would produce a large gap. These are consistency checks, not a labelled-ground-truth precision number.

## Feature engineering & league adjustment

`python -m features.build` writes `player_season_features` (one row per Understat player-season) and `league_strength` to the database.

- **Age** is decimal years on 1 January of the season's end year (mid-season), from Transfermarkt birth dates (known for 98.8% of rows).
- **Position group** (GK / DEF / MID / WING_AM / FWD) comes from Transfermarkt, with Understat's coarse label as fallback (99.8% known). Wingers and attacking mids are split from centre-forwards because their shot and chance profiles differ.
- **Per-90 rates** for goals, assists, xG, npxG, xA, shots, key passes, xG chain, xG build-up.
- **Percentiles** rank only players with 450+ minutes: `*_pct_league` within (league, season, position group), and `*_pct_global` within (season, position group) across all leagues on league-adjusted rates.

### League-strength adjustment

A fixed league ranking would be an assumption; instead the factor is estimated from players who actually changed league. A player's ability changes little over a season or two, so how their output (npxG + xA per 90) shifts after a move measures the difficulty gap. The model is a within-player regression with league effects and age/age² terms, estimated on 903 movers observed in different leagues within one season of each other, with 95% intervals from a cluster bootstrap over players:

| League | Factor | 95% interval |
|---|---|---|
| Ligue 1 | 1.095 | 1.04–1.14 |
| Bundesliga | 1.088 | 1.03–1.15 |
| Serie A | 1.045 | 1.00–1.10 |
| La Liga | 0.940 | 0.90–0.99 |
| EPL | 0.854 | 0.82–0.89 |

A factor of 0.85 means the same player typically produces ~15% less attacking output per 90 in the EPL than the average of the five leagues. Per-90 volume stats are divided by it to get comparable rates.

How far to trust it:
- **Supported:** the raw pairwise shifts are antisymmetric (every route *into* the EPL lowers output by 0.17–0.28 in log terms, every route *out* raises it by 0.12–0.17; Ligue 1 ↔ La Liga mirror each other too), which regression to the mean alone would not produce. A same-season-movers-only check (93 players) gives the same picture for the EPL (0.81) and Bundesliga (1.09).
- **Uncertain:** the order of the three middle leagues. Their intervals overlap and the same-season check reorders them.
- **Caveats:** movers are a selected group (regression to the mean after standout seasons can exaggerate gaps); the factor mixes difficulty with league style (the Bundesliga is goal-heavy); it is estimated on npxG + xA and applied to all volume-type attacking rates; only these five leagues are covered, so lower leagues need another source before the Hamza Abdelkarim case study can use it.
- **Defenders and goalkeepers (FBref):** tackles won, interceptions, crosses, fouls and fouls drawn per 90, with percentiles within (league, season, position group). These are *not* league-adjusted: the strength factor was fitted on attacking output and has not been validated for defensive actions. Goalkeepers get save percentage and shots on target faced per 90. Without post-shot xG, save% is a noisy quality proxy (percentile 71 for Alisson 2022 on 3,330 minutes), and percentiles rank raw values, so a higher percentile means a higher value, not necessarily better. Defenders' profiles are still thin compared with attackers' (no pressures, progressive passes or duels).
- **Data limit:** raw per-90 values for players with tiny minutes are meaningless (e.g. 2 minutes at 19 npxG/90); use the percentile columns or filter on minutes.

## Similarity engine

`python -m ml.comps "Erling Haaland" --season 2020` returns the closest comparable player-seasons and a gap analysis against them (`ml/similarity.py`, `ml/gap_analysis.py`).

What "comparable" controls for:
- **Position:** hard filter on position group.
- **Age:** hard window of +-1.5 years plus a soft penalty, because "what did players with this profile at 19 become" is the question the trajectory model asks.
- **League quality:** stats are the league-adjusted rates above; the league's strength and the size of the league jump from the previous season are separate context features.
- **Missing data:** a query uses only the features its target has. FBref's defensive stats do not exist before 2016, so a 2014 season is compared on attacking stats, against candidates that have them. The result reports which features were used.

Distance is a weighted sum of block distances (attack stats, defence stats, context, age) over z-scored square-root rates. The block weights are design judgements, **not tuned**: tuning them against the test below would only reward context features that persist across seasons.

**Choosing the metric without labels.** A player is the same person across seasons, so within the same position group and age window a player-season's *other* seasons should rank near the top of its neighbours. Over 13,300 targets (stats only, context off):

| Metric | hit@10 | MRR | by chance |
|---|---|---|---|
| Euclidean | **0.393** | **0.212** | 0.031 |
| Mahalanobis (shrunk covariance) | 0.383 | 0.206 | 0.031 |
| Cosine | 0.357 | 0.187 | 0.031 |

All three beat chance by roughly 12x, so the stats capture player style. The simplest metric wins (Mahalanobis's decorrelation does not help, cosine loses because it ignores magnitude), so Euclidean is the default. By position (Euclidean): midfielders 0.49 (chance 0.03), wingers/attacking mids 0.45 (0.04), forwards 0.40 (0.05), defenders 0.36 (0.02), **goalkeepers 0.15 (0.08)** since they have only two features. This measures whether the representation captures style, not whether comps predict careers; that is the backtest's job.

Example output (comps shown are distinct players, closest season each):

| Target | Closest comps |
|---|---|
| Lamine Yamal 2024/25 (age 17.5) | Ansu Fati 2019, Mastantuono 2025, Mathys Tel 2023, Lennart Karl 2025, Musiala 2021, Wirtz 2021 |
| Jamal Musiala 2021/22 (18.8) | Ibrahim Maza 2025, Ben Seghir 2024, Karl 2025, Bellingham 2022, Pulisic 2016, Vinicius Jr 2019 |
| Erling Haaland 2020/21 (20.4) | Sepe Wahi 2023, Luka Jovic 2018, Hojlund 2022, Esposito 2025, Sesko 2023, Isak 2020 |

The gap analysis then reads, for Haaland against those comps: strong on non-penalty xG (+19 percentile points) and build-up involvement; weak on tackles won, interceptions, crosses and fouls drawn (-18 to -23), which is what a pure striker should look like.

![Targets and their comps in PCA space](docs/comps_pca.png)

PCA of the engine's own stats space: PC1 is overall attacking output (all attacking features load the same way), PC2 separates finishers from chance-creators. Comps sit in a tight neighbourhood around the target (median distance to the target is about half that of a typical same-age, same-position player: 0.76 vs 1.46 for Haaland, 1.37 vs 2.43 for Yamal). Extreme profiles sit at the edge of the cloud, so their comps lie between them and the pack. PCA is a 2-D shadow of an ~11-dimensional space.

Limits to keep in mind:
- Comps are by statistical profile. The backtest below shows they do not predict careers better than simple baselines, so they serve as evidence, not as the headline probability.
- Without pressures, progressive passing or duels, the engine cannot separate a deep-lying holder from a box-to-box midfielder (Rodri's gap analysis shows him "weak" on tackles and interceptions mainly because his comps are not pure defensive midfielders).
- Pathway features are partial: league strength and league jump are in; transfer-history features (origin club tier, reserve vs first-team football) and non-top-5 origins are not, so the Hamza Abdelkarim case needs lower-league data first.

## Trajectory forecast and backtest

`python -m ml.project "Lamine Yamal" --season 2024` answers "what do players like this become?" with outcome probabilities and a range, a market-value range, and the comps as visible evidence (each with what it became). The honest story is in how it got built: the first design lost to simple baselines, and the headline model is now a different one.

**What "become" means** (`ml/outcomes.py`, horizon = next 3 seasons), defined two independent ways:
- **Performance tier:** peak of a position-specific composite percentile (league-adjusted attacking output) over the next three seasons, as *elite* (top decile), *good* (top quartile) or *regular*, or *out* when the player has no 900+ minute top-5 season in the window (left the five leagues, lost his place, retired, injured). Defenders and goalkeepers only get retained / out, because Understat says little about their quality.
- **Market value:** peak Transfermarkt squad-page value in the next three seasons divided by the value now, conditional on staying on a top-5 squad.

Windows that are not yet complete are never scored.

**The backtest** (`ml/backtest.py`) is rolling-origin: for each season 2018 to 2022 it rebuilds the features from data up to that season only (league-strength factors included), predicts the next three seasons for every player aged 23 or under with 900+ minutes (1,378 targets, 852 players), and scores against what happened. Leakage rule, asserted in code: every comp or training row used must have a *finished* outcome window by the origin date. Models are compared on Brier score, log loss and pinball loss, with 95% intervals bootstrapped over players, against:
- **B0** base rate for the same position and age (no model),
- **B1** "same level": the k players of that position and age closest on the one current number (composite percentile, or current market value), with the same shrinkage and k as the comps model; this tests whether multi-dimensional similarity earns its complexity,
- **comps**: outcomes of the 30 most similar players (the similarity engine above), shrunk toward the base rate,
- **learned**: regularised logistic regression (tiers) and gradient-boosted quantiles (value) on a few summary features (current level, age, minutes, last season's change, league strength and jump, market value).

Protocol: the comps configuration was fixed before any result was seen. The learned models were then developed on origins 2018 to 2020 only; 2021 to 2022 are reported separately as a holdout. (A first version of the learned model, with different regularisation, was seen on the holdout; no setting was chosen using it.)

| Lower is better | B0 base rate | B1 same level | comps | **learned** |
|---|---|---|---|---|
| Performance tier, Brier (n=824) | 0.617 | 0.582 | 0.598 | **0.512** |
| Performance tier, log loss | 1.176 | 1.078 | 1.134 | **0.897** |
| Same, holdout 2021 to 2022 (n=326), Brier | 0.641 | 0.589 | 0.607 | **0.516** |
| Retention, Brier (n=1,378) | 0.113 | 0.111 | 0.112 | **0.100** |
| Market value, pinball (n=1,313) | 0.181 | 0.177 | 0.186 | **0.166** |
| Market value, 80% interval coverage | 0.81 | 0.75 | 0.76 | 0.79 |

What the intervals say (model minus baseline, 95% interval; negative means the model is better):
- **Comps lose to "same level".** Performance Brier +0.017 [+0.007, +0.027]; market value pinball +0.009 [+0.005, +0.013]. They beat the base rate on tiers (-0.019 [-0.027, -0.010]) but add nothing for retention. Similar stats do not predict a career better than "how good is he now, and how old".
- **The learned model wins everywhere.** Versus same-level: performance Brier -0.069 [-0.095, -0.044] (holdout alone: -0.073 [-0.105, -0.042]), retention -0.010 [-0.013, -0.007], value pinball -0.011 [-0.014, -0.007].
- **Where the gain comes from.** Dropping market value barely matters (Brier 0.519 vs 0.512), so it is not just the market's opinion. A level-and-age-only version scores 0.539, still better than same-level matching (-0.043 [-0.062, -0.025]): a smooth fit over thousands of rows beats averaging 30 neighbours. Minutes, last season's trend and league add the rest.
- **Ranking:** AUC for "becomes elite" is 0.890 (current composite alone: 0.869). The top 10% by P(elite) were 41.5% elite against a 7.4% base rate.

So the comps are the *evidence* and the learned model is the *headline*. The forecast shows both: the comps' own outcome mix appears next to the model's probabilities.

Failure cases, not hidden:
- **Calibration:** the raw model overstates P(elite) between 20% and 70% (holdout: predicted 0.34, observed 0.16 for the 20 to 50% bucket). A Platt map fitted on out-of-time predictions fixes the buckets and improves holdout Brier from 0.516 to 0.510, but the log-loss gain has an interval spanning zero (-0.012 [-0.031, +0.012]), so it is a correction for a bias seen in both blocks, not a proven improvement. P(out) is well calibrated.
- **Confident misses of the learned model:** Fabian Ruiz and Jadon Sancho (P(elite) 0.84, both ended "good"), Alex Iwobi, Mason Mount, Gabriel Martinelli. **Breakouts it still undersold:** Vinicius Jr, Saka and Rodrygo got 0.17 to 0.36 (the comps said 0.01).
- **Thin early pool:** at the 2018 origin only 2014 and 2015 outcomes are known, so the comps model had about 11 usable comps per target; the other origins about 30.
- **Definitions matter:** "elite" is a stats composite at a fixed cut (top decile); "out" mixes injury, retirement and moving to a league outside the data; market value is only observed while on a top-5 squad; forecasts are capped at the highest value in the data (EUR 200m) because too few players sit near the top for the model to learn a ceiling. The 80% value interval covers 79% overall.
- **Scope:** top-5 leagues only, a 3-season horizon, attacking composites for outfield players. Lower-league and non-European origins (the Hamza Abdelkarim case) need other data.

## Known gaps

- StatsBomb is not yet linked to Transfermarkt (it has no club-season squad table to block on).
- Per-player history is fetched only for players with 900+ Understat minutes (`--min-minutes`), not the full ~9,400.
- A few players are missing from Transfermarkt squad pages (e.g. short loans); they stay unlinked rather than guessed.
