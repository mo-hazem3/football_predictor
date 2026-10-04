"""Send the pipeline models to the `pipeline` database and keep everything else on `default`.

The pipeline database is written by the data_pipeline/features CLIs, never by Django, so no
migration is ever allowed there (and the models are unmanaged anyway)."""

PIPELINE_APP = "pipeline_data"
PIPELINE_ALIAS = "pipeline"


class PipelineRouter:
    def db_for_read(self, model, **hints):
        return PIPELINE_ALIAS if model._meta.app_label == PIPELINE_APP else None

    def db_for_write(self, model, **hints):
        return PIPELINE_ALIAS if model._meta.app_label == PIPELINE_APP else None

    def allow_relation(self, obj1, obj2, **hints):
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if db == PIPELINE_ALIAS or app_label == PIPELINE_APP:
            return False
        return None
