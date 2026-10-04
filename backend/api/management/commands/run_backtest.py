from ._pipeline import PipelineCommand


class Command(PipelineCommand):
    help = "Run the rolling-origin trajectory backtest (wraps ml.backtest)"
    module = "ml.backtest"
