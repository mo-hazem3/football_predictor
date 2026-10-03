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
pytest
```

Downloads are cached under `data/cache/` (never re-fetched) and requests are rate-limited. Output lands in `data/db/football.sqlite`.

## Data caveats

StatsBomb open data covers only selected competitions/seasons (e.g. only Bayer Leverkusen for Bundesliga 2023/24), so it is the event-level source, not the backbone for career histories. FBref/Understat via `soccerdata` is the next step for breadth.
