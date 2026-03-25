from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    Usuario, FichaFisica, EjercicioCatalogo, PlanEntrenamiento, 
    DetalleRutina, BloqueHorario, Reserva, Notificacion
)

# Registramos el usuario personalizado usando la vista optimizada de Django
admin.site.register(Usuario, UserAdmin)

# Registramos el resto de los modelos
admin.site.register(FichaFisica)
admin.site.register(EjercicioCatalogo)
admin.site.register(PlanEntrenamiento)
admin.site.register(DetalleRutina)
admin.site.register(BloqueHorario)
admin.site.register(Reserva)
admin.site.register(Notificacion)