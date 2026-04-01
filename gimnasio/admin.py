from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    Usuario, FichaFisica, EjercicioCatalogo, PlanEntrenamiento, 
    DetalleRutina, BloqueHorario, Reserva, Notificacion
)

# Creamos una clase personalizada para decirle a Django qué campos extra mostrar
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Datos del Gimnasio', {
            'fields': ('rol', 'es_seleccionado', 'rama_deportiva', 'inasistencias_acumuladas', 'bloqueado_hasta'),
        }),
    )

# Registramos el usuario con nuestra nueva clase
admin.site.register(Usuario, CustomUserAdmin)

# Registramos el resto de los modelos
admin.site.register(FichaFisica)
admin.site.register(EjercicioCatalogo)
admin.site.register(PlanEntrenamiento)
admin.site.register(DetalleRutina)
admin.site.register(BloqueHorario)
admin.site.register(Reserva)
admin.site.register(Notificacion)