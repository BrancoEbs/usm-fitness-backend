from django.apps import AppConfig

class GimnasioConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'gimnasio'

    def ready(self):
        # Importamos las signals cuando la app arranca
        import gimnasio.signals