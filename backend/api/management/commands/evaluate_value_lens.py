from ._pipeline import PipelineCommand


class Command(PipelineCommand):
    help = "Backtest the value-versus-performance lens (wraps ml.evaluate_value_lens)"
    module = "ml.evaluate_value_lens"
