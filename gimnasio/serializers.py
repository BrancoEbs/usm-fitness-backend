from rest_framework import serializers
from .models import Usuario, BloqueHorario, Reserva, FichaFisica, EjercicioCatalogo, PlanEntrenamiento, DetalleRutina
from datetime import timedelta, date

class UsuarioResumenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ['id', 'first_name', 'last_name', 'es_seleccionado', 'rol', 'username']

class FichaFisicaSerializer(serializers.ModelSerializer):
    usuario = serializers.HiddenField(default=serializers.CurrentUserDefault())
    
    class Meta:
        model = FichaFisica
        fields = ['id', 'usuario', 'peso_kg', 'estatura_cm', 'objetivo_principal', 'observaciones_entrenador']
        read_only_fields = ['observaciones_entrenador']

class BloqueHorarioSerializer(serializers.ModelSerializer):
    entrenador_nombre = serializers.CharField(source='entrenador_a_cargo.get_full_name', read_only=True)
    cupos_disponibles = serializers.SerializerMethodField()
    
    class Meta:
        model = BloqueHorario
        # 1. AÑADIMOS 'codigo_bloque' a la lista
        fields = ['id', 'dia', 'codigo_bloque', 'hora_inicio', 'hora_fin', 'aforo_regular', 'entrenador_a_cargo', 'entrenador_nombre', 'cupos_disponibles']
        
        # 2. Le decimos a Django que NO pida las horas al crear, porque el modelo las calcula solas
        read_only_fields = ['hora_inicio', 'hora_fin']

    def get_cupos_disponibles(self, obj):
        hoy = date.today()
        reservas_hoy = Reserva.objects.filter(bloque=obj, fecha_especifica=hoy, estado__in=['PEN', 'PRE']).count()
        return max(0, obj.aforo_regular - reservas_hoy)

class ReservaSerializer(serializers.ModelSerializer):
    alumno = serializers.HiddenField(default=serializers.CurrentUserDefault())
    bloque_detalle = BloqueHorarioSerializer(source='bloque', read_only=True)
    alumno_nombre = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Reserva
        fields = ['id', 'alumno', 'alumno_nombre', 'bloque', 'bloque_detalle', 'fecha_especifica', 'estado']
        read_only_fields = ['estado']

    def get_alumno_nombre(self, obj):
        return f"{obj.alumno.first_name} {obj.alumno.last_name} ({obj.alumno.username})"

    def validate(self, data):
        alumno = data['alumno']
        
        if alumno.esta_bloqueado():
            raise serializers.ValidationError({"error": f"Estás bloqueado por inasistencias hasta el {alumno.bloqueado_hasta.strftime('%d-%m-%Y')}."})

        if Reserva.objects.filter(alumno=alumno, bloque=data['bloque'], fecha_especifica=data['fecha_especifica'], estado__in=['PEN', 'PRE']).exists():
            raise serializers.ValidationError({"error": "Ya tienes una reserva para este bloque."})
            
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
    # Esto es magia pura: Anida todos los ejercicios dentro del plan automáticamente
    rutina_interactiva = DetalleRutinaSerializer(many=True, read_only=True)
    creado_por_nombre = serializers.CharField(source='creado_por.get_full_name', read_only=True)

    class Meta:
        model = PlanEntrenamiento
        fields = ['id', 'titulo', 'es_global', 'archivo_adjunto', 'fecha_vencimiento', 'creado_por_nombre', 'rutina_interactiva']



class RegistroSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ['rut', 'first_name', 'last_name', 'carrera', 'password']
        extra_kwargs = {'password': {'write_only': True}} # Oculta la contraseña por seguridad

    def create(self, validated_data):
        rut = validated_data['rut']
        # El gran truco: Guardamos el RUT también como "username"
        user = Usuario.objects.create_user(
            username=rut, 
            rut=rut,
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            carrera=validated_data.get('carrera', ''),
            password=validated_data['password'],
            rol=1 # Todos nacen como Alumno Regular
        )
        return user