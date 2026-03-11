from django.apps import AppConfig


class PropertyManagersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.property_managers"
    verbose_name = "Property Managers"

    def ready(self):
        import apps.property_managers.signals  # noqa: F401
        from apps.property_managers.signals import connect_external_signals
        connect_external_signals()
