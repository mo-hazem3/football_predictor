from ._pipeline import PipelineCommand


class Command(PipelineCommand):
    help = "Ingest FBref via soccerdata (opens an automated Chrome) (wraps data_pipeline.ingest_fbref)"
    module = "data_pipeline.ingest_fbref"
