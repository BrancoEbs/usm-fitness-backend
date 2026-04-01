from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import BloqueHorarioViewSet, ReservaViewSet, UsuarioViewSet, FichaFisicaViewSet, EjercicioCatalogoViewSet, PlanEntrenamientoViewSet, DetalleRutinaViewSet, RegistroUsuarioView

router = DefaultRouter()
router.register(r'bloques', BloqueHorarioViewSet)
router.register(r'reservas', ReservaViewSet, basename='reserva')
router.register(r'usuarios', UsuarioViewSet)
router.register(r'fichas', FichaFisicaViewSet, basename='ficha')

# AÑADIMOS ESTAS DOS RUTAS:
router.register(r'ejercicios', EjercicioCatalogoViewSet)
router.register(r'planes', PlanEntrenamientoViewSet, basename='plan')
router.register(r'rutinas-detalle', DetalleRutinaViewSet)

urlpatterns = [
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    path('registro/', RegistroUsuarioView.as_view(), name='registro'),
    path('', include(router.urls)),
]