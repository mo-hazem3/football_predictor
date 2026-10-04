from ._pipeline import PipelineCommand


class Command(PipelineCommand):
    help = "Build the player-season feature table and league-strength factors (wraps features.build)"
    module = "features.build"
