from ._pipeline import PipelineCommand


class Command(PipelineCommand):
    help = "Ingest Transfermarkt squads and optional per-player value/transfer history (wraps data_pipeline.ingest_transfermarkt)"
    module = "data_pipeline.ingest_transfermarkt"
