import re
from datetime import date

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

from .models import (
    Usuario, BloqueHorario, Reserva, FichaFisica, EjercicioCatalogo,
    PlanEntrenamiento, DetalleRutina, ConfiguracionGimnasio, Rol,
)


# =====================================================================
# UTILIDADES DE VALIDACIÓN
# =====================================================================
def normalizar_rut(valor):
    """Quita puntos y espacios y deja la letra K en mayúscula (formato 12345678-9)."""
    return str(valor).replace('.', '').replace(' ', '').upper()


def rut_es_valido(rut):
    """Valida formato y dígito verificador (módulo 11) de un RUT chileno."""
    limpio = rut.replace('-', '')
    if not re.fullmatch(r'\d{7,8}[0-9K]', limpio):
        return False
    cuerpo, dv = limpio[:-1], limpio[-1]
    suma, factor = 0, 2
    for d in reversed(cuerpo):
        suma += int(d) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - (suma % 11)
    esperado = '0' if resto == 11 else 'K' if resto == 10 else str(resto)
    return dv == esperado


def validar_rango(valor, minimo, maximo, nombre):
    if valor is not None and not (minimo <= valor <= maximo):
        raise serializers.ValidationError(f'{nombre} debe estar entre {minimo} y {maximo}.')
    return valor


# =====================================================================
# USUARIOS
# =====================================================================
class UsuarioResumenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ['id', 'first_name', 'last_name', 'es_seleccionado', 'rol', 'username', 'rama_deportiva', 'carrera']
        read_only_fields = ['username']


class RegistroSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)
    first_name = serializers.CharField(required=True, max_length=150)
    last_name = serializers.CharField(required=True, max_length=150)
    carrera = serializers.CharField(required=False, allow_blank=True, max_length=100)

    class Meta:
        model = Usuario
        fields = ['username', 'password', 'first_name', 'last_name', 'email', 'carrera']
        extra_kwargs = {'password': {'write_only': True}}

    def validate_username(self, value):
        rut = normalizar_rut(value)
        if not rut_es_valido(rut):
            raise serializers.ValidationError('El RUT no es válido.')
        if Usuario.objects.filter(username__iexact=rut).exists():
            raise serializers.ValidationError('Ya existe una cuenta con este RUT.')
        return rut

    def validate_email(self, value):
        correo = value.strip().lower()
        dominio = correo.rsplit('@', 1)[-1]
        if dominio not in settings.DOMINIOS_CORREO_PERMITIDOS:
            permitidos = ', '.join('@' + d for d in settings.DOMINIOS_CORREO_PERMITIDOS)
            raise serializers.ValidationError(f'Debes usar tu correo institucional ({permitidos}).')
        if Usuario.objects.filter(email__iexact=correo).exists():
            raise serializers.ValidationError('Ya existe una cuenta con este correo.')
        return correo

    def validate(self, data):
        for campo in ('first_name', 'last_name', 'carrera'):
            if data.get(campo):
                data[campo] = data[campo].strip().title()

        # Política de contraseñas de Django (largo mínimo, comunes, solo números, similitud)
        candidato = Usuario(username=data.get('username'), first_name=data.get('first_name', ''),
                            last_name=data.get('last_name', ''), email=data.get('email', ''))
        try:
            validate_password(data.get('password', ''), user=candidato)
        except DjangoValidationError as e:
            raise serializers.ValidationError({'password': list(e.messages)})
        return data

    def create(self, validated_data):
        validated_data['password'] = make_password(validated_data['password'])
        validated_data['rol'] = Rol.ALUMNO  # nunca se acepta el rol desde el cliente
        return super().create(validated_data)


# =====================================================================
# FICHA FÍSICA
# =====================================================================
class FichaFisicaSerializer(serializers.ModelSerializer):
    class Meta:
        model = FichaFisica
        fields = [
            'id', 'usuario', 'carrera_normalizada', 'peso_kg', 'estatura_cm',
            'porcentaje_grasa', 'masa_muscular', 'perimetro_cintura',
            'condicion_cardiaca', 'dolor_pecho', 'mareos_desmayos',
            'lesion_articular', 'medicacion_presion', 'recomendacion_medica',
            'lesiones_previas', 'objetivo_principal', 'observaciones_entrenador',
            'fecha_actualizacion'
        ]
        # Las observaciones solo las escribe el staff mediante /actualizar_nota/
        read_only_fields = ['usuario', 'fecha_actualizacion', 'observaciones_entrenador']
        extra_kwargs = {
            'carrera_normalizada': {'max_length': 100},
            'lesiones_previas': {'max_length': 2000},
            'objetivo_principal': {'max_length': 2000},
        }

    def validate_peso_kg(self, v):
        return validar_rango(v, 20, 300, 'El peso (kg)')

    def validate_estatura_cm(self, v):
        return validar_rango(v, 100, 250, 'La estatura (cm)')

    def validate_porcentaje_grasa(self, v):
        return validar_rango(v, 0, 70, 'El porcentaje de grasa')

    def validate_masa_muscular(self, v):
        return validar_rango(v, 0, 200, 'La masa muscular')

    def validate_perimetro_cintura(self, v):
        return validar_rango(v, 30, 250, 'El perímetro de cintura (cm)')


# =====================================================================
# BLOQUES Y RESERVAS
# =====================================================================
class BloqueHorarioSerializer(serializers.ModelSerializer):
    entrenador_nombre = serializers.CharField(source='entrenador_a_cargo.get_full_name', read_only=True)
    cupos_disponibles = serializers.SerializerMethodField()

    class Meta:
        model = BloqueHorario
        fields = ['id', 'fecha', 'dia', 'codigo_bloque', 'hora_inicio', 'hora_fin', 'aforo_regular',
                  'entrenador_a_cargo', 'entrenador_nombre', 'cupos_disponibles']
        read_only_fields = ['hora_inicio', 'hora_fin']

    def validate_fecha(self, value):
        if value and value < date.today():
            raise serializers.ValidationError("No puedes crear bloques para fechas pasadas.")
        return value

    def validate_aforo_regular(self, value):
        return validar_rango(value, 0, 200, 'El aforo')

    def validate_entrenador_a_cargo(self, value):
        if value is not None and value.rol != Rol.ENTRENADOR:
            raise serializers.ValidationError('El usuario asignado no es entrenador.')
        return value

    def get_cupos_disponibles(self, obj):
        reservas_activas = Reserva.objects.filter(bloque=obj, estado__in=['PEN', 'PRE']).count()
        return max(0, obj.aforo_regular - reservas_activas)


class ReservaSerializer(serializers.ModelSerializer):
    alumno = serializers.HiddenField(default=serializers.CurrentUserDefault())
    bloque_detalle = BloqueHorarioSerializer(source='bloque', read_only=True)
    alumno_nombre = serializers.SerializerMethodField(read_only=True)
    fecha_especifica = serializers.DateField(required=False)

    class Meta:
        model = Reserva
        fields = ['id', 'alumno', 'alumno_nombre', 'bloque', 'bloque_detalle', 'fecha_especifica', 'estado', 'es_sobrecupo']
        read_only_fields = ['estado', 'es_sobrecupo']

    def get_alumno_nombre(self, obj):
        return f"{obj.alumno.first_name} {obj.alumno.last_name} ({obj.alumno.username})"

    def validate(self, data):
        alumno = data['alumno']
        # Se bloquea la fila del bloque para que dos reservas simultáneas no superen el aforo
        bloque = BloqueHorario.objects.select_for_update().get(id=data['bloque'].id)

        # La fecha de la reserva es siempre la del bloque (no la que envíe el cliente)
        fecha = bloque.fecha or data.get('fecha_especifica')
        if fecha is None:
            raise serializers.ValidationError({"error": "El bloque no tiene fecha asignada."})
        data['fecha_especifica'] = fecha

        ahora = timezone.localtime(timezone.now())
        if fecha < ahora.date() or (fecha == ahora.date() and bloque.hora_inicio < ahora.time()):
            raise serializers.ValidationError({"error": "No puedes reservar un bloque que ya comenzó."})

        if alumno.esta_bloqueado():
            raise serializers.ValidationError({"error": f"Estás bloqueado por inasistencias hasta el {timezone.localtime(alumno.bloqueado_hasta).strftime('%d-%m-%Y')}."})

        reserva_existente = Reserva.objects.filter(
            alumno=alumno, fecha_especifica=fecha, estado__in=['PEN', 'PRE']
        ).first()
        if reserva_existente:
            modulo = (reserva_existente.bloque.codigo_bloque or '').replace('B', '')
            raise serializers.ValidationError({
                "error": f"Ya tienes una reserva ese día para el Módulo {modulo}. Solo se permite 1 módulo por día."
            })

        reservas_activas = Reserva.objects.filter(bloque=bloque, estado__in=['PEN', 'PRE']).count()
        if reservas_activas >= bloque.aforo_regular:
            if not alumno.es_seleccionado:
                raise serializers.ValidationError({"error": "Este módulo ya alcanzó su capacidad máxima."})
            data['es_sobrecupo'] = True
        else:
            data['es_sobrecupo'] = False
        return data


# =====================================================================
# ENTRENAMIENTO
# =====================================================================
class EjercicioCatalogoSerializer(serializers.ModelSerializer):
    video_url = serializers.URLField(required=False, allow_null=True, allow_blank=True)

    class Meta:
        model = EjercicioCatalogo
        fields = '__all__'

    def validate_video_url(self, value):
        if value and not value.lower().startswith(('https://', 'http://')):
            raise serializers.ValidationError('El enlace debe comenzar con http:// o https://')
        return value or None


class DetalleRutinaSerializer(serializers.ModelSerializer):
    ejercicio_detalle = EjercicioCatalogoSerializer(source='ejercicio', read_only=True)

    class Meta:
        model = DetalleRutina
        fields = ['id', 'plan', 'ejercicio', 'ejercicio_detalle', 'series', 'repeticiones', 'descanso_segundos', 'notas']

    def validate_series(self, v):
        return validar_rango(v, 1, 50, 'Las series')

    def validate_descanso_segundos(self, v):
        return validar_rango(v, 0, 3600, 'El descanso (segundos)')


class PlanEntrenamientoSerializer(serializers.ModelSerializer):
    rutina_interactiva = DetalleRutinaSerializer(many=True, read_only=True)
    creado_por_nombre = serializers.CharField(source='creado_por.get_full_name', read_only=True)
    archivo_adjunto = serializers.FileField(write_only=True, required=False, allow_null=True)
    archivo_url = serializers.SerializerMethodField()

    class Meta:
        model = PlanEntrenamiento
        fields = ['id', 'titulo', 'es_global', 'alumno_asignado', 'archivo_adjunto', 'archivo_url',
                  'fecha_vencimiento', 'creado_por_nombre', 'rutina_interactiva']

    def get_archivo_url(self, obj):
        # El PDF solo se descarga a través del endpoint autenticado
        return f'/api/planes/{obj.id}/archivo/' if obj.archivo_adjunto else None

    def validate_archivo_adjunto(self, archivo):
        if archivo is None:
            return archivo
        maximo = settings.TAMANO_MAXIMO_PDF_MB * 1024 * 1024
        if archivo.size > maximo:
            raise serializers.ValidationError(f'El PDF no puede superar {settings.TAMANO_MAXIMO_PDF_MB} MB.')
        if not archivo.name.lower().endswith('.pdf'):
            raise serializers.ValidationError('Solo se permiten archivos PDF.')
        inicio = archivo.read(5)
        archivo.seek(0)
        if inicio != b'%PDF-':
            raise serializers.ValidationError('El archivo no es un PDF válido.')
        return archivo

    def validate_alumno_asignado(self, value):
        if value is not None and value.rol != Rol.ALUMNO:
            raise serializers.ValidationError('El plan personal debe asignarse a un alumno.')
        return value

    def validate_fecha_vencimiento(self, value):
        if self.instance is None and value < date.today():
            raise serializers.ValidationError('La fecha de vencimiento no puede estar en el pasado.')
        return value


class ConfiguracionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfiguracionGimnasio
        fields = ['gimnasio_abierto', 'mensaje_cierre']
