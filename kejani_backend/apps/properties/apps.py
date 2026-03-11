from django.apps import AppConfig

class PropertiesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.properties"
    verbose_name = "Properties"

    def ready(self):
        # Import signals module so all signal handlers are registered
        # when Django starts. Without this, handlers never fire.
        import apps.properties.signals  # noqa
