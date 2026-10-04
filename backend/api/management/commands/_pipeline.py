"""Shared base for management commands that wrap the framework-agnostic pipeline CLIs.

The data_pipeline/features/ml packages own their argument parsing (and know nothing about Django), so these
commands hand the raw command line straight to that module's `main(argv)` instead of re-declaring every option:

    python manage.py ingest_understat --leagues EPL Bundesliga --seasons 2020 2025
    python manage.py ingest_understat --help        # the pipeline's own help
"""
import importlib
import sys

from django.core.management.base import BaseCommand


class PipelineCommand(BaseCommand):
    module: str = ""  # dotted path of a module exposing main(argv) -> int

    def create_parser(self, prog_name, subcommand, **kwargs):
        parser = super().create_parser(prog_name, subcommand, **kwargs)
        parser.add_argument("args", nargs="*", help=f"passed to {self.module} (use --help to list them)")
        return parser

    def run_from_argv(self, argv):
        # bypass Django's own parser: the wrapped CLI has options Django does not know
        code = importlib.import_module(self.module).main(argv[2:])
        sys.exit(code or 0)

    def handle(self, *args, **options):  # reached via call_command(...) without options
        code = importlib.import_module(self.module).main(list(options.get("args") or []))
        if code:
            sys.exit(code)
