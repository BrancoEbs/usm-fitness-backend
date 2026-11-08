import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenBlacklistView

from .models import (
    BloqueHorario, Reserva, Usuario, FichaFisica, EjercicioCatalogo,
    PlanEntrenamiento, DetalleRutina, ConfiguracionGimnasio, Rol,
)
from .serializers import (
    BloqueHorarioSerializer, ReservaSerializer, UsuarioResumenSerializer,
    FichaFisicaSerializer, EjercicioCatalogoSerializer, PlanEntrenamientoSerializer,
    DetalleRutinaSerializer, RegistroSerializer, ConfiguracionSerializer,
)

logger = logging.getLogger('gimnasio')


# =====================================================================
# PERMISOS POR ROL
# =====================================================================
class IsAdminUserRole(permissions.BasePermission):
    message = 'Solo los administradores pueden realizar esta acción.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.rol == Rol.ADMIN)


class IsTrainerOrAdmin(permissions.BasePermission):
    message = 'Solo entrenadores o administradores pueden realizar esta acción.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.rol in (Rol.ENTRENADOR, Rol.ADMIN))


def es_staff(user):
    return user.is_authenticated and user.rol in (Rol.ENTRENADOR, Rol.ADMIN)


def _a_bool(valor):
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str) and valor.strip().lower() in ('true', '1', 'si', 'sí'):
        return True
    if isinstance(valor, str) and valor.strip().lower() in ('false', '0', 'no', ''):
        return False
    if isinstance(valor, int) and valor in (0, 1):
        return bool(valor)
    raise ValidationError({'error': 'Valor booleano inválido.'})


# =====================================================================
# AUTENTICACIÓN (con límite de intentos)
# =====================================================================
class LoginView(TokenObtainPairView):
    throttle_scope = 'login'


class RefreshView(TokenRefreshView):
    pass


class LogoutView(TokenBlacklistView):
    """Invalida el refresh token recibido (cierre de sesión en el servidor)."""
    pass


# =====================================================================
# USUARIOS
# =====================================================================
class UsuarioViewSet(viewsets.ModelViewSet):
    queryset = Usuario.objects.all().order_by('last_name', 'first_name')
    serializer_class = UsuarioResumenSerializer
    throttle_scope = None  # la acción 'registro' usa el límite 'registro'

    def get_permissions(self):
        if self.action == 'registro':
            return [AllowAny()]
        if self.action == 'me':
            return [permissions.IsAuthenticated()]
        if self.action in ('list', 'retrieve'):
            return [IsTrainerOrAdmin()]
        # create, update, partial_update, destroy, buscar, actualizar_permisos
        return [IsAdminUserRole()]

    @action(detail=False, methods=['post'], authentication_classes=[], throttle_scope='registro')
    def registro(self, request):
        serializer = RegistroSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario = serializer.save()
        logger.info('Registro de nuevo usuario id=%s', usuario.id)
        return Response({"mensaje": "Usuario registrado exitosamente."}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def buscar(self, request):
        rol_usm = request.query_params.get('rol_usm', None)
        if rol_usm:
            try:
                user = Usuario.objects.get(username=rol_usm.replace('.', '').replace(' ', '').upper())
                return Response(self.get_serializer(user).data)
            except Usuario.DoesNotExist:
                return Response({"error": "Usuario no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"error": "Debe proporcionar un rol_usm."}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def me(self, request):
        data = self.get_serializer(request.user).data
        try:
            ficha = FichaFisica.objects.get(usuario=request.user)
            data['ficha_fisica'] = FichaFisicaSerializer(ficha).data
        except FichaFisica.DoesNotExist:
            data['ficha_fisica'] = None
        return Response(data)

    @action(detail=True, methods=['patch'])
    def actualizar_permisos(self, request, pk=None):
        usuario = self.get_object()
        rol = request.data.get('rol')
        es_seleccionado = request.data.get('es_seleccionado')
        rama_deportiva = request.data.get('rama_deportiva')

        if rol is not None:
            try:
                rol = int(rol)
            except (TypeError, ValueError):
                raise ValidationError({'error': 'Rol inválido.'})
            if rol not in Rol.values:
                raise ValidationError({'error': 'Rol inválido.'})
            if usuario.pk == request.user.pk and rol != Rol.ADMIN:
                raise ValidationError({'error': 'No puedes quitarte a ti mismo el rol de administrador.'})
            usuario.rol = rol

        if es_seleccionado is not None:
            usuario.es_seleccionado = _a_bool(es_seleccionado)

        if usuario.es_seleccionado:
            if rama_deportiva is not None:
                rama = str(rama_deportiva).strip()[:100]
                usuario.rama_deportiva = rama or None
        else:
            usuario.rama_deportiva = None

        usuario.save()
        logger.info('Permisos actualizados: usuario id=%s por admin id=%s (rol=%s, seleccionado=%s)',
                    usuario.id, request.user.id, usuario.rol, usuario.es_seleccionado)
        return Response({'mensaje': 'Permisos del usuario actualizados correctamente.'})

    def perform_destroy(self, instance):
        if instance.pk == self.request.user.pk:
            raise ValidationError({'error': 'No puedes eliminar tu propia cuenta.'})
        logger.warning('Usuario id=%s eliminado por admin id=%s', instance.id, self.request.user.id)
        instance.delete()


# =====================================================================
# BLOQUES HORARIOS
# =====================================================================
class BloqueHorarioViewSet(viewsets.ModelViewSet):
    serializer_class = BloqueHorarioSerializer

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy', 'forzar_generacion'):
            return [IsAdminUserRole()]
        if self.action in ('reservas_hoy', 'modificar_bloque'):
            return [IsTrainerOrAdmin()]
        return [permissions.IsAuthenticated()]

    def _generar_bloques_semana(self, lunes):
        dias = ['LU', 'MA', 'MI', 'JU', 'VI']
        codigos = ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8']

        for i, dia in enumerate(dias):
            fecha_actual = lunes + timedelta(days=i)
            for codigo in codigos:
                if not BloqueHorario.objects.filter(fecha=fecha_actual, codigo_bloque=codigo).exists():
                    bloque_previo = BloqueHorario.objects.filter(dia=dia, codigo_bloque=codigo).order_by('-fecha').first()
                    BloqueHorario(
                        fecha=fecha_actual,
                        dia=dia,
                        codigo_bloque=codigo,
                        aforo_regular=bloque_previo.aforo_regular if bloque_previo else 20,
                        entrenador_a_cargo=bloque_previo.entrenador_a_cargo if bloque_previo else None,
                    ).save()

    def get_queryset(self):
        ahora = timezone.localtime(timezone.now())
        hoy = ahora.date()
        hora_actual = ahora.time()

        lunes_actual = hoy - timedelta(days=hoy.weekday())
        domingo_actual = lunes_actual + timedelta(days=6)

        # Generación automática de la semana (actual, o la siguiente en fin de semana)
        if hoy.weekday() >= 5:
            lunes_proximo = hoy + timedelta(days=(7 - hoy.weekday()))
            if not BloqueHorario.objects.filter(fecha=lunes_proximo).exists():
                self._generar_bloques_semana(lunes_proximo)
        else:
            if not BloqueHorario.objects.filter(fecha=lunes_actual).exists():
                self._generar_bloques_semana(lunes_actual)

        # Reservas pendientes de bloques ya terminados pasan a Ausente
        bloques_pasados = BloqueHorario.objects.filter(
            Q(fecha__lt=hoy) | Q(fecha=hoy, hora_fin__lt=hora_actual)
        )
        Reserva.objects.filter(bloque__in=bloques_pasados, estado='PEN').update(estado='AUS')

        if es_staff(self.request.user):
            return BloqueHorario.objects.filter(
                fecha__range=[lunes_actual, domingo_actual]
            ).order_by('fecha', 'hora_inicio')

        return BloqueHorario.objects.filter(
            Q(fecha__gt=hoy) | Q(fecha=hoy, hora_inicio__gte=hora_actual)
        ).order_by('fecha', 'hora_inicio')

    @action(detail=False, methods=['post'])
    def forzar_generacion(self, request):
        hoy = timezone.localtime(timezone.now()).date()
        lunes_proximo = hoy + timedelta(days=(7 - hoy.weekday()))
        self._generar_bloques_semana(lunes_proximo)
        return Response({"mensaje": f"Semana del {lunes_proximo.strftime('%d-%m-%Y')} generada con éxito."})

    @action(detail=True, methods=['get'])
    def reservas_hoy(self, request, pk=None):
        bloque = self.get_object()
        reservas = Reserva.objects.filter(bloque=bloque).exclude(estado='CAN')
        return Response(ReservaSerializer(reservas, many=True).data)

    @action(detail=True, methods=['patch'])
    def modificar_bloque(self, request, pk=None):
        bloque = self.get_object()

        if 'aforo_regular' in request.data:
            try:
                aforo = int(request.data.get('aforo_regular'))
            except (TypeError, ValueError):
                raise ValidationError({'error': 'El aforo debe ser un número entero.'})
            if not 0 <= aforo <= 200:
                raise ValidationError({'error': 'El aforo debe estar entre 0 y 200.'})
            bloque.aforo_regular = aforo

        if 'entrenador_a_cargo' in request.data:
            entrenador_id = request.data.get('entrenador_a_cargo')
            if entrenador_id:
                try:
                    bloque.entrenador_a_cargo = Usuario.objects.get(id=int(entrenador_id), rol=Rol.ENTRENADOR)
                except (Usuario.DoesNotExist, TypeError, ValueError):
                    raise ValidationError({'error': 'El entrenador no existe.'})
            else:
                bloque.entrenador_a_cargo = None

        bloque.save()
        return Response(self.get_serializer(bloque).data)


# =====================================================================
# RESERVAS
# =====================================================================
class ReservaViewSet(viewsets.ModelViewSet):
    serializer_class = ReservaSerializer
    # Las reservas no se editan ni eliminan directamente: se cancelan o se marca asistencia.
    http_method_names = ['get', 'post', 'head', 'options']

    def get_permissions(self):
        if self.action == 'marcar_asistencia':
            return [IsTrainerOrAdmin()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        if es_staff(self.request.user):
            return Reserva.objects.all().order_by('-fecha_creacion')
        return Reserva.objects.filter(alumno=self.request.user).order_by('-fecha_creacion')

    @action(detail=True, methods=['post'])
    def cancelar(self, request, pk=None):
        reserva = self.get_object()
        if reserva.estado == 'PEN':
            reserva.estado = 'CAN'
            reserva.save()
            return Response({"mensaje": "Reserva cancelada."})
        return Response({"error": "No se puede cancelar."}, status=400)

    @action(detail=True, methods=['post'])
    def marcar_asistencia(self, request, pk=None):
        reserva = self.get_object()
        estado = request.data.get('estado')
        if estado not in ['PRE', 'AUS', 'PEN']:
            return Response({'error': 'Estado inválido'}, status=400)
        reserva.estado = estado
        reserva.save()
        logger.info('Asistencia: reserva id=%s -> %s por usuario id=%s', reserva.id, estado, request.user.id)
        return Response({'mensaje': 'Asistencia registrada', 'estado_actual': estado})

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        # El aforo, el sobrecupo, el bloqueo y la regla de 1 reserva por día se
        # validan en ReservaSerializer.validate con la fila del bloque bloqueada.
        config = ConfiguracionGimnasio.load()
        if not config.gimnasio_abierto:
            raise ValidationError({"error": config.mensaje_cierre})

        try:
            bloque = BloqueHorario.objects.get(id=int(request.data.get('bloque')))
        except (BloqueHorario.DoesNotExist, TypeError, ValueError):
            raise ValidationError({"error": "El bloque no existe."})

        if Reserva.objects.filter(bloque=bloque, alumno=request.user, estado__in=['PEN', 'PRE']).exists():
            raise ValidationError({"error": "Ya tienes una reserva activa para este horario."})

        return super().create(request, *args, **kwargs)


# =====================================================================
# FICHA FÍSICA
# =====================================================================
class FichaFisicaViewSet(viewsets.ModelViewSet):
    serializer_class = FichaFisicaSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    def get_permissions(self):
        if self.action in ('por_alumno', 'actualizar_nota'):
            return [IsTrainerOrAdmin()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        # Lectura: el staff ve todas las fichas; el alumno, solo la suya.
        # Edición de datos de la ficha: siempre solo la propia.
        if es_staff(user) and self.action in ('list', 'retrieve', 'por_alumno', 'actualizar_nota'):
            return FichaFisica.objects.all()
        return FichaFisica.objects.filter(usuario=user)

    def perform_create(self, serializer):
        if FichaFisica.objects.filter(usuario=self.request.user).exists():
            raise ValidationError({'error': 'Ya tienes una ficha física; edítala en lugar de crear otra.'})
        serializer.save(usuario=self.request.user)

    @action(detail=False, methods=['get'])
    def por_alumno(self, request):
        alumno_id = request.query_params.get('alumno_id')
        try:
            alumno_id = int(alumno_id)
        except (TypeError, ValueError):
            return Response({"error": "Falta alumno_id válido"}, status=400)
        try:
            ficha = FichaFisica.objects.get(usuario_id=alumno_id)
        except FichaFisica.DoesNotExist:
            return Response({"error": "Este alumno aún no ha completado su Ficha Física."}, status=404)
        return Response(self.get_serializer(ficha).data)

    @action(detail=True, methods=['patch'])
    def actualizar_nota(self, request, pk=None):
        ficha = self.get_object()
        nota = str(request.data.get('observaciones_entrenador', ''))[:5000]
        ficha.observaciones_entrenador = nota
        ficha.save()
        return Response({'mensaje': 'Observaciones actualizadas con éxito.', 'observaciones_entrenador': nota})


# =====================================================================
# ENTRENAMIENTO
# =====================================================================
class EjercicioCatalogoViewSet(viewsets.ModelViewSet):
    queryset = EjercicioCatalogo.objects.all()
    serializer_class = EjercicioCatalogoSerializer

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsTrainerOrAdmin()]
        return [permissions.IsAuthenticated()]


class PlanEntrenamientoViewSet(viewsets.ModelViewSet):
    serializer_class = PlanEntrenamientoSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve', 'archivo'):
            return [permissions.IsAuthenticated()]
        return [IsTrainerOrAdmin()]

    def get_queryset(self):
        hoy = timezone.localtime(timezone.now()).date()
        user = self.request.user
        base_query = PlanEntrenamiento.objects.filter(fecha_vencimiento__gte=hoy)
        if es_staff(user):
            return base_query.order_by('-fecha_vencimiento')
        return base_query.filter(Q(es_global=True) | Q(alumno_asignado=user)).order_by('-fecha_vencimiento')

    def perform_create(self, serializer):
        serializer.save(creado_por=self.request.user)

    @action(detail=True, methods=['get'])
    def archivo(self, request, pk=None):
        """Entrega el PDF del plan solo a quien puede ver el plan."""
        plan = self.get_object()
        if not plan.archivo_adjunto:
            raise Http404('El plan no tiene archivo adjunto.')
        respuesta = FileResponse(plan.archivo_adjunto.open('rb'), content_type='application/pdf')
        respuesta['Content-Disposition'] = f'inline; filename="plan_{plan.id}.pdf"'
        return respuesta


class DetalleRutinaViewSet(viewsets.ModelViewSet):
    queryset = DetalleRutina.objects.all()
    serializer_class = DetalleRutinaSerializer
    permission_classes = [IsTrainerOrAdmin]


# =====================================================================
# CONFIGURACIÓN DEL GIMNASIO
# =====================================================================
class ConfiguracionView(APIView):
    def get_permissions(self):
        if self.request.method == 'PATCH':
            return [IsAdminUserRole()]
        return [permissions.IsAuthenticated()]

    def get(self, request):
        return Response(ConfiguracionSerializer(ConfiguracionGimnasio.load()).data)

    def patch(self, request):
        config = ConfiguracionGimnasio.load()
        serializer = ConfiguracionSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        logger.info('Configuración del gimnasio cambiada por admin id=%s: %s', request.user.id, serializer.data)
        return Response(serializer.data)
