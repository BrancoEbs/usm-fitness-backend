from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

class Rol(models.IntegerChoices):
    ALUMNO = 1, 'Alumno Regular'
    ENTRENADOR = 2, 'Entrenador'
    ADMIN = 3, 'Administrador'

class Usuario(AbstractUser):
    rol = models.IntegerField(choices=Rol.choices, default=Rol.ALUMNO)
    es_seleccionado = models.BooleanField(default=False)
    rama_deportiva = models.CharField(max_length=100, blank=True, null=True) # Ej: Balonmano, Fútbol
    rut = models.CharField(max_length=20, unique=True, null=True, blank=True)
    carrera = models.CharField(max_length=100, null=True, blank=True)
    
    # Sistema de Penalizaciones (No-Show)
    inasistencias_acumuladas = models.PositiveIntegerField(default=0)
    bloqueado_hasta = models.DateTimeField(blank=True, null=True)

    def esta_bloqueado(self):
        if self.bloqueado_hasta:
            return timezone.now() < self.bloqueado_hasta
        return False


class FichaFisica(models.Model):
    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, related_name='ficha')
    peso_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    estatura_cm = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fecha_evaluacion = models.DateField(auto_now_add=True)
    lesiones_previas = models.TextField(blank=True, null=True)
    objetivo_principal = models.CharField(max_length=200, blank=True, null=True)
    observaciones_entrenador = models.TextField(blank=True, null=True)

class EjercicioCatalogo(models.Model):
    nombre = models.CharField(max_length=150)
    grupo_muscular = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)
    video_url = models.URLField(blank=True, null=True)

class PlanEntrenamiento(models.Model):
    titulo = models.CharField(max_length=200)
    es_global = models.BooleanField(default=False)
    archivo_adjunto = models.FileField(upload_to='planes_pdf/', blank=True, null=True)
    fecha_vencimiento = models.DateField()
    
    # Relaciones
    creado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, related_name='planes_creados')
    alumno_asignado = models.ForeignKey(Usuario, on_delete=models.CASCADE, blank=True, null=True, related_name='planes_personales')

class DetalleRutina(models.Model):
    plan = models.ForeignKey(PlanEntrenamiento, on_delete=models.CASCADE, related_name='rutina_interactiva')
    ejercicio = models.ForeignKey(EjercicioCatalogo, on_delete=models.CASCADE)
    series = models.PositiveIntegerField()
    repeticiones = models.CharField(max_length=50) # Ej: "10-12" o "Al fallo"
    descanso_segundos = models.PositiveIntegerField(default=60)
    notas = models.CharField(max_length=255, blank=True, null=True)


DIAS_SEMANA = [
    ('LU', 'Lunes'),
    ('MA', 'Martes'),
    ('MI', 'Miércoles'),
    ('JU', 'Jueves'),
    ('VI', 'Viernes'),
    ('SA', 'Sábado'),
]

class BloqueHorario(models.Model):
    BLOQUES_ESTANDAR = [
        ('B1', 'Bloque 1 (08:15 - 09:25)'),
        ('B2', 'Bloque 2 (09:40 - 10:50)'),
        ('B3', 'Bloque 3 (11:05 - 12:15)'),
        ('B4', 'Bloque 4 (12:30 - 13:40)'),
        ('B5', 'Bloque 5 (14:40 - 15:50)'),
        ('B6', 'Bloque 6 (16:05 - 17:15)'),
        ('B7', 'Bloque 7 (17:30 - 18:40)'),
        ('B8', 'Bloque 8 (18:50 - 20:00)'), 
    ]

    dia = models.CharField(max_length=2, choices=DIAS_SEMANA)
    fecha = models.DateField(null=True, blank=True)
    codigo_bloque = models.CharField(max_length=2, choices=BLOQUES_ESTANDAR, null=True, blank=True)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    aforo_regular = models.IntegerField(default=20)
    entrenador_a_cargo = models.ForeignKey('Usuario', on_delete=models.SET_NULL, null=True, blank=True, limit_choices_to={'rol': 2})

    def save(self, *args, **kwargs):
        # Mapeo automático de horas exactas
        horas = {
            'B1': ("08:15", "09:25"),
            'B2': ("09:40", "10:50"),
            'B3': ("11:05", "12:15"),
            'B4': ("12:30", "13:40"),
            'B5': ("14:40", "15:50"),
            'B6': ("16:05", "17:15"),
            'B7': ("17:30", "18:40"),
            'B8': ("18:50", "20:00"), 
        }
        if self.codigo_bloque in horas:
            self.hora_inicio, self.hora_fin = horas[self.codigo_bloque]
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_dia_display()} - {self.codigo_bloque if self.codigo_bloque else self.hora_inicio}"


class EstadoAsistencia(models.TextChoices):
    PENDIENTE = 'PEN', 'Pendiente'
    PRESENTE = 'PRE', 'Presente'
    AUSENTE = 'AUS', 'Ausente'
    CANCELADA = 'CAN', 'Cancelada' # Si el alumno cancela a tiempo

class Reserva(models.Model):
    alumno = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='mis_reservas')
    bloque = models.ForeignKey(BloqueHorario, on_delete=models.CASCADE, related_name='reservas')
    fecha_especifica = models.DateField() # La fecha real del calendario (Ej: 09-03-2026)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=3, choices=EstadoAsistencia.choices, default=EstadoAsistencia.PENDIENTE)
    es_sobrecupo = models.BooleanField(default=False) # Para saber visualmente si entró por cupo de selección

class Notificacion(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='notificaciones')
    titulo = models.CharField(max_length=150)
    mensaje = models.TextField()
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    leida = models.BooleanField(default=False)

class ConfiguracionGimnasio(models.Model):
    gimnasio_abierto = models.BooleanField(default=True)
    mensaje_cierre = models.CharField(
        max_length=255, 
        default="El gimnasio se encuentra cerrado por receso universitario o mantención."
    )

    def save(self, *args, **kwargs):
        self.pk = 1 # Truco Singleton: Forzamos a que siempre reemplace la fila 1
        super(ConfiguracionGimnasio, self).save(*args, **kwargs)

    @classmethod
    def load(cls):
        # Si no existe la configuración, la crea. Si existe, la trae.
        obj, created = cls.objects.get_or_create(pk=1)
        return obj