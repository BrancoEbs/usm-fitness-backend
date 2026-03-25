from rest_framework import serializers
from .models import Usuario, BloqueHorario, Reserva, FichaFisica
from datetime import timedelta

class UsuarioResumenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ['id', 'first_name', 'last_name', 'es_seleccionado', 'rama_deportiva']

class BloqueHorarioSerializer(serializers.ModelSerializer):
    entrenador_nombre = serializers.CharField(source='entrenador_a_cargo.get_full_name', read_only=True)
    
    class Meta:
        model = BloqueHorario
        fields = ['id', 'dia', 'hora_inicio', 'hora_fin', 'aforo_regular', 'sobrecupos_seleccionados', 'entrenador_nombre']

class ReservaSerializer(serializers.ModelSerializer):
    alumno_detalle = UsuarioResumenSerializer(source='alumno', read_only=True)
    bloque_detalle = BloqueHorarioSerializer(source='bloque', read_only=True)

    class Meta:
        model = Reserva
        fields = ['id', 'alumno', 'alumno_detalle', 'bloque', 'bloque_detalle', 'fecha_especifica', 'estado', 'es_sobrecupo']
        read_only_fields = ['estado', 'es_sobrecupo']

    def validate(self, data):
        """
        Aquí ocurre la magia. Validamos todas las reglas de negocio antes de guardar.
        """
        alumno = data['alumno']
        bloque = data['bloque']
        fecha = data['fecha_especifica']

        # 1. Validar si el alumno está suspendido por inasistencias
        if alumno.esta_bloqueado():
            raise serializers.ValidationError({"error": "Estás suspendido por inasistencias y no puedes reservar."})

        # 2. Validar límite de reservas semanales (3 para regulares, 5 para seleccionados)
        # Calculamos el inicio (Lunes) y fin (Domingo) de la semana de la reserva
        inicio_semana = fecha - timedelta(days=fecha.weekday())
        fin_semana = inicio_semana + timedelta(days=6)

        # Contamos cuántas reservas activas (Pendientes o Presentes) tiene esa semana
        reservas_semana = Reserva.objects.filter(
            alumno=alumno,
            fecha_especifica__range=[inicio_semana, fin_semana],
            estado__in=['PEN', 'PRE']
        ).count()

        limite_semanal = 5 if alumno.es_seleccionado else 3
        if reservas_semana >= limite_semanal:
            raise serializers.ValidationError({"error": f"Has alcanzado tu límite de {limite_semanal} reservas para esta semana."})

        # 3. Validar Aforo y Sobrecupos del Bloque
        # Contamos cuántas personas ya reservaron este mismo bloque este mismo día
        reservas_actuales = Reserva.objects.filter(
            bloque=bloque,
            fecha_especifica=fecha,
            estado__in=['PEN', 'PRE']
        ).count()

        if reservas_actuales < bloque.aforo_regular:
            # Hay espacio regular, todo bien.
            data['es_sobrecupo'] = False
        else:
            # El aforo regular está lleno. Revisamos si puede tomar sobrecupo.
            if not alumno.es_seleccionado:
                raise serializers.ValidationError({"error": "El bloque está lleno. No hay cupos regulares disponibles."})
            else:
                cupos_totales = bloque.aforo_regular + bloque.sobrecupos_seleccionados
                if reservas_actuales < cupos_totales:
                    # Entra como sobrecupo
                    data['es_sobrecupo'] = True
                else:
                    raise serializers.ValidationError({"error": "El bloque está completamente lleno (incluyendo sobrecupos)."})

        return data