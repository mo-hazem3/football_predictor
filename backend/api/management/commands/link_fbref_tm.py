from ._pipeline import PipelineCommand


class Command(PipelineCommand):
    help = "Link FBref players to Transfermarkt players (wraps data_pipeline.link_fbref_tm)"
    module = "data_pipeline.link_fbref_tm"
