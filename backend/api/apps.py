import threading

from django.apps import AppConfig


class ApiConfig(AppConfig):
    name = "api"

    def ready(self):
        from django.conf import settings

        if settings.PRELOAD_MODELS:
            from .services import get_service

            # load in the background so the server accepts connections (and /health/ answers) meanwhile
            threading.Thread(target=get_service, name="preload-models", daemon=True).start()
