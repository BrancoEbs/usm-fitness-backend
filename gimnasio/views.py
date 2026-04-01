from rest_framework import viewsets, permissions, status, generics
from rest_framework.permissions import AllowAny
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth.hashers import make_password
from datetime import date, timedelta
from .models import BloqueHorario, Reserva, Usuario, FichaFisica, EjercicioCatalogo, PlanEntrenamiento, DetalleRutina
from .serializers import BloqueHorarioSerializer, ReservaSerializer, UsuarioResumenSerializer, FichaFisicaSerializer, EjercicioCatalogoSerializer, PlanEntrenamientoSerializer, DetalleRutinaSerializer, RegistroSerializer
from django.db.models import Q

class IsAdminUserRole(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.rol == 3

class IsTrainerOrAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.rol in [2, 3]

class UsuarioViewSet(viewsets.ModelViewSet):
    queryset = Usuario.objects.all()
    serializer_class = UsuarioResumenSerializer

    def get_permissions(self):
        if self.action == 'registro':
            return [permissions.AllowAny()]
        elif self.action in ['update', 'partial_update', 'buscar']:
            return [IsAdminUserRole()]
        return [permissions.IsAuthenticated()]

    @action(detail=False, methods=['post'])
    def registro(self, request):
        data = request.data
        if Usuario.objects.filter(username=data.get('username')).exists():
            return Response({"error": "Este Rol USM o RUT ya está registrado."}, status=status.HTTP_400_BAD_REQUEST)
        user = Usuario.objects.create(
            username=data.get('username'), password=make_password(data.get('password')),
            first_name=data.get('first_name', ''), last_name=data.get('last_name', ''),
            rol=1, es_seleccionado=False
        )
        return Response({"mensaje": "Cuenta creada exitosamente."}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def buscar(self, request):
        rol_usm = request.query_params.get('rol_usm', None)
        if rol_usm:
            try:
                user = Usuario.objects.get(username=rol_usm)
                return Response(self.get_serializer(user).data)
            except Usuario.DoesNotExist:
                return Response({"error": "Usuario no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"error": "Debe proporcionar un rol_usm."}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        data = serializer.data
        try:
            ficha = FichaFisica.objects.get(usuario=request.user)
            data['ficha_fisica'] = FichaFisicaSerializer(ficha).data
        except FichaFisica.DoesNotExist:
            data['ficha_fisica'] = None
        return Response(data)

class BloqueHorarioViewSet(viewsets.ModelViewSet):
    queryset = BloqueHorario.objects.all().order_by('dia', 'hora_inicio')
    serializer_class = BloqueHorarioSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUserRole()]
        return [permissions.IsAuthenticated()]

    @action(detail=True, methods=['get'], permission_classes=[IsTrainerOrAdmin])
    def reservas_hoy(self, request, pk=None):
        bloque = self.get_object()
        hoy = date.today()
        reservas = Reserva.objects.filter(bloque=bloque, fecha_especifica=hoy).exclude(estado='CAN')
        serializer = ReservaSerializer(reservas, many=True)
        return Response(serializer.data)

class ReservaViewSet(viewsets.ModelViewSet):
    serializer_class = ReservaSerializer
    
    def get_queryset(self):
        if self.request.user.rol in [2, 3]:
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

    @action(detail=True, methods=['post'], permission_classes=[IsTrainerOrAdmin])
    def marcar_asistencia(self, request, pk=None):
        reserva = self.get_object()
        estado = request.data.get('estado')

        if estado not in ['PRE', 'AUS']:
            return Response({'error': 'Estado inválido'}, status=400)

        if reserva.estado == 'PEN':
            reserva.estado = estado
            reserva.save()
            return Response({'mensaje': 'Asistencia guardada'})
        return Response({'error': 'La asistencia ya fue tomada'}, status=400)

class FichaFisicaViewSet(viewsets.ModelViewSet):
    serializer_class = FichaFisicaSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_queryset(self):
        return FichaFisica.objects.filter(usuario=self.request.user)

class EjercicioCatalogoViewSet(viewsets.ModelViewSet):
    queryset = EjercicioCatalogo.objects.all()
    serializer_class = EjercicioCatalogoSerializer
    
    def get_permissions(self):
        # Solo Entrenadores y Admins pueden crear/editar ejercicios. Alumnos solo ven.
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsTrainerOrAdmin()]
        return [permissions.IsAuthenticated()]

class PlanEntrenamientoViewSet(viewsets.ModelViewSet):
    serializer_class = PlanEntrenamientoSerializer
    
    def get_queryset(self):
        user = self.request.user
        if user.rol in [2, 3]:
            return PlanEntrenamiento.objects.all().order_by('-fecha_vencimiento')
        return PlanEntrenamiento.objects.filter(
            Q(es_global=True) | Q(alumno_asignado=user)
        ).order_by('-fecha_vencimiento')

    # NUEVO: Guarda automáticamente quién creó el plan
    def perform_create(self, serializer):
        serializer.save(creado_por=self.request.user)

# NUEVO: Endpoint para guardar los ejercicios dentro del plan
class DetalleRutinaViewSet(viewsets.ModelViewSet):
    queryset = DetalleRutina.objects.all()
    serializer_class = DetalleRutinaSerializer
    permission_classes = [IsTrainerOrAdmin]

class RegistroUsuarioView(generics.CreateAPIView):
    queryset = Usuario.objects.all()
    permission_classes = [AllowAny] # Permite entrar sin estar logueado
    serializer_class = RegistroSerializer