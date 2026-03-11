from django.apps import AppConfig

class LandlordsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.landlords'
    verbose_name = 'Landlords'

    def ready(self):
        import apps.landlords.signals  # noqa — registers signal handlers on startup
