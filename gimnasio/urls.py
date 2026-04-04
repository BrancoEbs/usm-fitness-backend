from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import BloqueHorarioViewSet, ReservaViewSet, UsuarioViewSet, FichaFisicaViewSet, EjercicioCatalogoViewSet, PlanEntrenamientoViewSet, DetalleRutinaViewSet, ConfiguracionView # Quité RegistroUsuarioView

router = DefaultRouter()
router.register(r'bloques', BloqueHorarioViewSet, basename='bloques')
router.register(r'reservas', ReservaViewSet, basename='reserva')
router.register(r'usuarios', UsuarioViewSet)
router.register(r'fichafisica', FichaFisicaViewSet, basename='fichafisica')
router.register(r'ejercicios', EjercicioCatalogoViewSet)
router.register(r'planes', PlanEntrenamientoViewSet, basename='plan')
router.register(r'detallerutina', DetalleRutinaViewSet)

urlpatterns = [
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('configuracion/', ConfiguracionView.as_view(), name='configuracion'),
    path('', include(router.urls)),
]