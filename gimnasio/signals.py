from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from .models import Reserva, EstadoAsistencia

@receiver(pre_save, sender=Reserva)
def penalizar_inasistencia(sender, instance, **kwargs):
    """
    Se ejecuta justo antes de que una Reserva se guarde en la BD.
    Compara el estado anterior con el nuevo para detectar si se marcó como AUSENTE.
    """
    if instance.id: # Solo si la reserva ya existía (no aplica al crearla por primera vez)
        try:
            reserva_anterior = Reserva.objects.get(id=instance.id)
            
            # Si antes NO era ausente, y ahora SÍ es ausente...
            if reserva_anterior.estado != EstadoAsistencia.AUSENTE and instance.estado == EstadoAsistencia.AUSENTE:
                alumno = instance.alumno
                alumno.inasistencias_acumuladas += 1
                
                # Regla de Negocio: 3 faltas = Bloqueo de 7 días
                if alumno.inasistencias_acumuladas >= 3:
                    alumno.bloqueado_hasta = timezone.now() + timedelta(days=7)
                    alumno.inasistencias_acumuladas = 0 # Reiniciamos el contador
                
                # Guardamos los cambios en el perfil del alumno
                alumno.save()
                
        except Reserva.DoesNotExist:
            pass