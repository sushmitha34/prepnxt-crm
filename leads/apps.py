from django.apps import AppConfig


class LeadsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "leads"

    def ready(self):
        # Importing for the side effect of registering the @receiver handlers.
        # Without this, signals.py is never imported and the lead-claiming
        # signal silently never fires.
        from . import signals  # noqa: F401