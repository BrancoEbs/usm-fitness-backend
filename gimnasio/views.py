from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import BloqueHorario, Reserva, EstadoAsistencia
from .serializers import BloqueHorarioSerializer, ReservaSerializer

class BloqueHorarioViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Endpoint para que los alumnos vean los bloques disponibles.
    Usamos ReadOnly porque los alumnos no deben crear bloques desde la app.
    """
    queryset = BloqueHorario.objects.all().order_by('dia', 'hora_inicio')
    serializer_class = BloqueHorarioSerializer

class ReservaViewSet(viewsets.ModelViewSet):
    queryset = Reserva.objects.all().order_by('-fecha_creacion')
    serializer_class = ReservaSerializer

    # ... (Aquí va tu código actual, si tienes alguno extra)

    @action(detail=True, methods=['patch'])
    def marcar_asistencia(self, request, pk=None):
        """
        Endpoint rápido para que el entrenador marque la asistencia.
        Ruta: PATCH /api/reservas/{id}/marcar_asistencia/
        """
        reserva = self.get_object()
        nuevo_estado = request.data.get('estado')

        # Validamos que el estado enviado sea correcto
        if nuevo_estado not in [EstadoAsistencia.PRESENTE, EstadoAsistencia.AUSENTE]:
            return Response(
                {"error": "Estado inválido. Debe ser 'PRE' (Presente) o 'AUS' (Ausente)."}, 
                status=400
            )

        # Actualizamos y guardamos. 
        # ¡Al hacer save(), la signal de signals.py se disparará automáticamente!
        reserva.estado = nuevo_estado
        reserva.save()

        return Response({
            "mensaje": f"Asistencia actualizada a {nuevo_estado}",
            "alumno": reserva.alumno.get_full_name(),
            "inasistencias_actuales": reserva.alumno.inasistencias_acumuladas,
            "bloqueado_hasta": reserva.alumno.bloqueado_hasta
        })