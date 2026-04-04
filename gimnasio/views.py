from rest_framework import viewsets, permissions, status
from rest_framework.permissions import AllowAny
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth.hashers import make_password
from datetime import timedelta
from .models import BloqueHorario, Reserva, Usuario, FichaFisica, EjercicioCatalogo, PlanEntrenamiento, DetalleRutina, ConfiguracionGimnasio
from .serializers import BloqueHorarioSerializer, ReservaSerializer, UsuarioResumenSerializer, FichaFisicaSerializer, EjercicioCatalogoSerializer, PlanEntrenamientoSerializer, DetalleRutinaSerializer, RegistroSerializer, ConfiguracionSerializer
from django.db.models import Q
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

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
        # 1. Dejamos pasar libremente a los que se están registrando
        if self.action == 'registro':
            return [AllowAny()]
            
        # 2. Reglas para administradores
        if self.action in ['update', 'partial_update', 'buscar']:
            return [IsAdminUserRole()]
            
        # 3. Para todo lo demás (ver perfil, etc), debes haber iniciado sesión
        return [permissions.IsAuthenticated()]

    @action(detail=False, methods=['post'], authentication_classes=[])
    def registro(self, request):
        # Usamos tu serializador especializado para el registro
        serializer = RegistroSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"mensaje": "Usuario registrado exitosamente."}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
    
    @action(detail=True, methods=['patch'])
    def actualizar_permisos(self, request, pk=None):
        if request.user.rol != 3:
            return Response({"error": "No tienes permisos de Administrador."}, status=403)

        usuario = self.get_object()
        rol = request.data.get('rol')
        es_seleccionado = request.data.get('es_seleccionado')
        rama_deportiva = request.data.get('rama_deportiva') # <-- NUEVO

        if rol is not None:
            usuario.rol = rol
        if es_seleccionado is not None:
            usuario.es_seleccionado = es_seleccionado
            # Si le quitan el check de seleccionado, limpiamos la rama
            if not es_seleccionado:
                usuario.rama_deportiva = None
        
        # Guardamos la rama (incluso si viene vacía para limpiarla)
        if rama_deportiva is not None or es_seleccionado is False:
            usuario.rama_deportiva = rama_deportiva if es_seleccionado else None
            
        usuario.save()
        return Response({'mensaje': 'Permisos del usuario actualizados correctamente.'})

class BloqueHorarioViewSet(viewsets.ModelViewSet):
    serializer_class = BloqueHorarioSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'forzar_generacion']:
            return [IsAdminUserRole()]
        return [permissions.IsAuthenticated()]

    def _generar_bloques_semana(self, lunes):
        dias = ['LU', 'MA', 'MI', 'JU', 'VI']
        codigos = ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8']
        
        for i, dia in enumerate(dias):
            fecha_actual = lunes + timedelta(days=i)
            for codigo in codigos:
                # Si no existe el bloque, lo creamos basándonos en el historial
                if not BloqueHorario.objects.filter(fecha=fecha_actual, codigo_bloque=codigo).exists():
                    # Buscamos el último bloque idéntico para copiar su entrenador y aforo
                    bloque_previo = BloqueHorario.objects.filter(dia=dia, codigo_bloque=codigo).order_by('-fecha').first()
                    entrenador = bloque_previo.entrenador_a_cargo if bloque_previo else None
                    aforo = bloque_previo.aforo_regular if bloque_previo else 20
                    
                    b = BloqueHorario(
                        fecha=fecha_actual,
                        dia=dia,
                        codigo_bloque=codigo,
                        aforo_regular=aforo,
                        entrenador_a_cargo=entrenador
                    )
                    b.save()

    def get_queryset(self):
        ahora = timezone.localtime(timezone.now())
        hoy = ahora.date()
        hora_actual = ahora.time()

        # --- MAGIA AUTO-GENERADORA ---
        if hoy.weekday() >= 5: # Si es Sábado (5) o Domingo (6)
            lunes_proximo = hoy + timedelta(days=(7 - hoy.weekday()))
            if not BloqueHorario.objects.filter(fecha=lunes_proximo).exists():
                self._generar_bloques_semana(lunes_proximo)
        else: # Si es Lunes a Viernes
            lunes_actual = hoy - timedelta(days=hoy.weekday())
            if not BloqueHorario.objects.filter(fecha=lunes_actual).exists():
                self._generar_bloques_semana(lunes_actual)
        # -----------------------------

        # Limpieza de bloques pasados
        bloques_pasados = BloqueHorario.objects.filter(
            Q(fecha__lt=hoy) | Q(fecha=hoy, hora_fin__lt=hora_actual)
        )
        Reserva.objects.filter(bloque__in=bloques_pasados, estado='PEN').update(estado='AUS')

        user = self.request.user
        if user.rol in [2, 3]:
            return BloqueHorario.objects.all().order_by('-fecha', 'hora_inicio')
        
        return BloqueHorario.objects.filter(
            Q(fecha__gt=hoy) | Q(fecha=hoy, hora_inicio__gte=hora_actual)
        ).order_by('fecha', 'hora_inicio')

    @action(detail=False, methods=['post'], permission_classes=[IsAdminUserRole])
    def forzar_generacion(self, request):
        ahora = timezone.localtime(timezone.now())
        hoy = ahora.date()
        # Calcula el próximo lunes desde hoy
        lunes_proximo = hoy + timedelta(days=(7 - hoy.weekday()))
        self._generar_bloques_semana(lunes_proximo)
        return Response({"mensaje": f"Semana del {lunes_proximo.strftime('%d-%m-%Y')} generada con éxito."})

    @action(detail=True, methods=['get'], permission_classes=[IsTrainerOrAdmin])
    def reservas_hoy(self, request, pk=None):
        bloque = self.get_object()
        reservas = Reserva.objects.filter(bloque=bloque).exclude(estado='CAN')
        serializer = ReservaSerializer(reservas, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['patch'])
    def modificar_bloque(self, request, pk=None):
        bloque = self.get_object()
        
        # Leemos con el nombre correcto que mandará React
        entrenador_id = request.data.get('entrenador_a_cargo')
        aforo = request.data.get('aforo_regular')
        
        if aforo is not None:
            bloque.aforo_regular = int(aforo)
            
        # Revisamos si viene la instrucción de cambiar al entrenador
        if 'entrenador_a_cargo' in request.data:
            if entrenador_id:
                from .models import Usuario 
                try:
                    # Buscamos al usuario real
                    nuevo_entrenador = Usuario.objects.get(id=int(entrenador_id))
                    # Y se lo asignamos A LA COLUMNA CORRECTA
                    bloque.entrenador_a_cargo = nuevo_entrenador 
                except Usuario.DoesNotExist:
                    return Response({"error": "El entrenador no existe en la BD."}, status=400)
            else:
                bloque.entrenador_a_cargo = None
                
        bloque.save()
        
        serializer = self.get_serializer(bloque)
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

        if estado not in ['PRE', 'AUS', 'PEN']:
            return Response({'error': 'Estado inválido'}, status=400)

        # Quitamos la restricción. Ahora el entrenador puede corregir un error 
        # (ej: cambiar de Ausente a Presente si el alumno llegó tarde).
        reserva.estado = estado
        reserva.save()
        return Response({'mensaje': 'Asistencia registrada', 'estado_actual': estado})

    @transaction.atomic  # <-- Esto crea la transacción segura
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

class FichaFisicaViewSet(viewsets.ModelViewSet):
    serializer_class = FichaFisicaSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # Si es Entrenador o Admin, puede ver todas las fichas. Si es alumno, solo la suya.
        if user.rol in [2, 3]:
            return FichaFisica.objects.all()
        return FichaFisica.objects.filter(usuario=user)

    # NUEVO: Endpoint para buscar la ficha de un alumno específico
    @action(detail=False, methods=['get'], permission_classes=[IsTrainerOrAdmin])
    def por_alumno(self, request):
        alumno_id = request.query_params.get('alumno_id')
        if not alumno_id:
            return Response({"error": "Falta alumno_id"}, status=400)
        try:
            ficha = FichaFisica.objects.get(usuario_id=alumno_id)
            serializer = self.get_serializer(ficha)
            return Response(serializer.data)
        except FichaFisica.DoesNotExist:
            return Response({"error": "Este alumno aún no ha completado su Ficha Física."}, status=404)

    # NUEVO: Acción exclusiva para que el entrenador ponga notas (Ignora el read_only_field)
    @action(detail=True, methods=['patch'], permission_classes=[IsTrainerOrAdmin])
    def actualizar_nota(self, request, pk=None):
        ficha = self.get_object()
        nota = request.data.get('observaciones_entrenador', '')
        
        ficha.observaciones_entrenador = nota
        ficha.save()
        
        return Response({'mensaje': 'Observaciones actualizadas con éxito.', 'observaciones_entrenador': nota})

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
        # --- MAGIA AUTO-ELIMINADORA ---
        hoy = timezone.localtime(timezone.now()).date()
        # Elimina silenciosamente cualquier plan cuya fecha de vencimiento sea anterior a hoy
        PlanEntrenamiento.objects.filter(fecha_vencimiento__lt=hoy).delete()
        # ------------------------------

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


class ConfiguracionView(APIView):
    def get(self, request):
        config = ConfiguracionGimnasio.load()
        serializer = ConfiguracionSerializer(config)
        return Response(serializer.data)

    def patch(self, request):
        if request.user.rol != 3:
            return Response({"error": "Solo administradores pueden cambiar esto."}, status=403)
        
        config = ConfiguracionGimnasio.load()
        serializer = ConfiguracionSerializer(config, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)