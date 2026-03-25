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


class DiaSemana(models.TextChoices):
    LUNES = 'LU', 'Lunes'
    MARTES = 'MA', 'Martes'
    MIERCOLES = 'MI', 'Miércoles'
    JUEVES = 'JU', 'Jueves'
    VIERNES = 'VI', 'Viernes'

class BloqueHorario(models.Model):
    dia = models.CharField(max_length=2, choices=DiaSemana.choices)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    aforo_regular = models.PositiveIntegerField(default=20)
    sobrecupos_seleccionados = models.PositiveIntegerField(default=5)
    entrenador_a_cargo = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name='bloques_asignados')

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