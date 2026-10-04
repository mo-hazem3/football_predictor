import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from api import services


class Command(BaseCommand):
    help = ("Fit the forecaster, value table, aging curves and team profiles from the pipeline database and pickle them, "
            "so the API starts in seconds. Re-run after any change to the pipeline database.")

    def add_arguments(self, parser):
        parser.add_argument("--bootstraps", type=int, default=settings.FORECAST_BOOTSTRAPS,
                            help="bootstrap refits behind the forecast ranges (default: FORECAST_BOOTSTRAPS)")
        parser.add_argument("--output", default=str(settings.FORECAST_CACHE_PATH))

    def handle(self, *args, **options):
        db_path, out = Path(settings.PIPELINE_DB_PATH), Path(options["output"])
        if not db_path.exists():
            self.stderr.write(f"No pipeline database at {db_path}. Run the ingest and build_features commands first.")
            raise SystemExit(1)
        start = time.time()
        service = services.build_from_database(db_path, options["bootstraps"])
        services.write_cache(service, out, db_path, options["bootstraps"])
        self.stdout.write(self.style.SUCCESS(
            f"Built in {time.time() - start:.0f}s: {len(service.index)} players, {len(service.out)} player-seasons, "
            f"{len(service.teams) if service.teams is not None else 0} team-seasons -> {out} ({out.stat().st_size / 1e6:.0f} MB)"))
