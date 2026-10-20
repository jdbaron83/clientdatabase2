from django.apps import AppConfig


class RecordsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "records"
    verbose_name = "Client records"

    def ready(self):
        from . import audit  # noqa: F401  (registers signal handlers)
