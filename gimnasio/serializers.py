from rest_framework import serializers
from .models import Usuario, BloqueHorario, Reserva, FichaFisica, EjercicioCatalogo, PlanEntrenamiento, DetalleRutina, ConfiguracionGimnasio
from datetime import timedelta, date
from django.contrib.auth.hashers import make_password 

class UsuarioResumenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ['id', 'first_name', 'last_name', 'es_seleccionado', 'rol', 'username', 'rama_deportiva','carrera']

class FichaFisicaSerializer(serializers.ModelSerializer):
    usuario = serializers.HiddenField(default=serializers.CurrentUserDefault())
    
    class Meta:
        model = FichaFisica
        # Agregamos 'lesiones_previas' a la lista de campos
        fields = ['id', 'usuario', 'peso_kg', 'estatura_cm', 'lesiones_previas', 'objetivo_principal', 'observaciones_entrenador']
        read_only_fields = ['observaciones_entrenador']

class BloqueHorarioSerializer(serializers.ModelSerializer):
    entrenador_nombre = serializers.CharField(source='entrenador_a_cargo.get_full_name', read_only=True)
    cupos_disponibles = serializers.SerializerMethodField()
    
    class Meta:
        model = BloqueHorario
        # AÑADIMOS 'fecha' A LA LISTA
        fields = ['id', 'fecha', 'dia', 'codigo_bloque', 'hora_inicio', 'hora_fin', 'aforo_regular', 'entrenador_a_cargo', 'entrenador_nombre', 'cupos_disponibles']
        read_only_fields = ['hora_inicio', 'hora_fin']

    # VALIDACIÓN: Evita crear bloques en el pasado
    def validate_fecha(self, value):
        if value < date.today():
            raise serializers.ValidationError("No puedes crear bloques para fechas pasadas.")
        return value

    def get_cupos_disponibles(self, obj):
        # Simplificado: Ya no necesitamos buscar por fecha específica porque el bloque tiene fecha
        reservas_activas = Reserva.objects.filter(bloque=obj, estado__in=['PEN', 'PRE']).count()
        return max(0, obj.aforo_regular - reservas_activas)

class ReservaSerializer(serializers.ModelSerializer):
    alumno = serializers.HiddenField(default=serializers.CurrentUserDefault())
    bloque_detalle = BloqueHorarioSerializer(source='bloque', read_only=True)
    alumno_nombre = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Reserva
        # Añadimos 'es_sobrecupo' a la lista para que el frontend lo pueda ver
        fields = ['id', 'alumno', 'alumno_nombre', 'bloque', 'bloque_detalle', 'fecha_especifica', 'estado', 'es_sobrecupo']
        read_only_fields = ['estado', 'es_sobrecupo']

    def get_alumno_nombre(self, obj):
        return f"{obj.alumno.first_name} {obj.alumno.last_name} ({obj.alumno.username})"

    def validate(self, data):
        alumno = data['alumno']
        fecha = data['fecha_especifica']
        bloque = BloqueHorario.objects.select_for_update().get(id=data['bloque'].id)
        
        # Validación 1: ¿Está bloqueado por inasistencias?
        if alumno.esta_bloqueado():
            raise serializers.ValidationError({"error": f"Estás bloqueado por inasistencias hasta el {alumno.bloqueado_hasta.strftime('%d-%m-%Y')}."})

        # Validación 2: REGLA DE UN BLOQUE POR DÍA
        reserva_existente = Reserva.objects.filter(
            alumno=alumno, 
            fecha_especifica=fecha, 
            estado__in=['PEN', 'PRE']
        ).first()

        if reserva_existente:
            raise serializers.ValidationError({
                "error": f"Ya tienes una reserva hoy para el Módulo {reserva_existente.bloque.codigo_bloque.replace('B', '')}. Solo se permite 1 módulo por día."
            })

        # Validación 3: CONTROL DE AFORO Y SOBRECUPOS (LA MAGIA)
        reservas_activas = Reserva.objects.filter(
            bloque=bloque, 
            estado__in=['PEN', 'PRE']
        ).count()

        if reservas_activas >= bloque.aforo_regular:
            if not alumno.es_seleccionado:
                raise serializers.ValidationError({"error": "Este módulo ya alcanzó su capacidad máxima."})
            else:
                # Si es seleccionado y el bloque está lleno, lo marcamos como sobrecupo
                data['es_sobrecupo'] = True
        else:
            data['es_sobrecupo'] = False
            
        return data

class EjercicioCatalogoSerializer(serializers.ModelSerializer):
    class Meta:
        model = EjercicioCatalogo
        fields = '__all__'

class DetalleRutinaSerializer(serializers.ModelSerializer):
    ejercicio_detalle = EjercicioCatalogoSerializer(source='ejercicio', read_only=True)

    class Meta:
        model = DetalleRutina
        # AÑADIMOS 'plan' A ESTA LISTA:
        fields = ['id', 'plan', 'ejercicio', 'ejercicio_detalle', 'series', 'repeticiones', 'descanso_segundos', 'notas']

class PlanEntrenamientoSerializer(serializers.ModelSerializer):
    rutina_interactiva = DetalleRutinaSerializer(many=True, read_only=True)
    creado_por_nombre = serializers.CharField(source='creado_por.get_full_name', read_only=True)

    class Meta:
        model = PlanEntrenamiento
        # AÑADIMOS 'alumno_asignado' a la lista
        fields = ['id', 'titulo', 'es_global', 'alumno_asignado', 'archivo_adjunto', 'fecha_vencimiento', 'creado_por_nombre', 'rutina_interactiva']

class RegistroSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        # Aquí pedimos exactamente lo que manda el formulario de React
        fields = ['username', 'password', 'first_name', 'last_name', 'carrera']
        # Esto asegura que la contraseña nunca viaje de vuelta en respuestas por seguridad
        extra_kwargs = {'password': {'write_only': True}}

    def validate(self, data):
        # 1. Limpiar y estandarizar Nombres
        if 'first_name' in data and data['first_name']:
            data['first_name'] = data['first_name'].strip().title()
            
        # 2. Limpiar y estandarizar Apellidos
        if 'last_name' in data and data['last_name']:
            data['last_name'] = data['last_name'].strip().title()

        # 3. Limpiar y estandarizar Carrera
        if 'carrera' in data and data['carrera']:
            data['carrera'] = data['carrera'].strip().title()

        # 4. Estandarizar RUT (Todo a mayúscula, sin puntos, espacios ni guiones)
        if 'username' in data and data['username']:
            data['username'] = str(data['username']).replace('.', '').replace(' ', '').upper()

        return super().validate(data)

    def create(self, validated_data):
        # Encriptamos la contraseña obligatoriamente antes de guardar en la BD
        validated_data['password'] = make_password(validated_data['password'])
        return super().create(validated_data)
    
class ConfiguracionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfiguracionGimnasio
        fields = ['gimnasio_abierto', 'mensaje_cierre']