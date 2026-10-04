from ._pipeline import PipelineCommand


class Command(PipelineCommand):
    help = "Ingest StatsBomb open data (wraps data_pipeline.ingest_statsbomb)"
    module = "data_pipeline.ingest_statsbomb"
