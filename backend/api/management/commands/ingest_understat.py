from ._pipeline import PipelineCommand


class Command(PipelineCommand):
    help = "Ingest Understat player-season stats (wraps data_pipeline.ingest_understat)"
    module = "data_pipeline.ingest_understat"
