from ._pipeline import PipelineCommand


class Command(PipelineCommand):
    help = "Link Understat players to Transfermarkt players (wraps data_pipeline.link_understat_tm)"
    module = "data_pipeline.link_understat_tm"
