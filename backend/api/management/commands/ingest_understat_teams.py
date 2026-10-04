from ._pipeline import PipelineCommand


class Command(PipelineCommand):
    help = "Ingest Understat team match stats and tactical-style breakdowns (wraps data_pipeline.ingest_understat_teams)"
    module = "data_pipeline.ingest_understat_teams"
