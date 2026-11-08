from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    BloqueHorarioViewSet, ReservaViewSet, UsuarioViewSet, FichaFisicaViewSet,
    EjercicioCatalogoViewSet, PlanEntrenamientoViewSet, DetalleRutinaViewSet,
    ConfiguracionView, LoginView, RefreshView, LogoutView,
)

router = DefaultRouter()
router.register(r'bloques', BloqueHorarioViewSet, basename='bloques')
router.register(r'reservas', ReservaViewSet, basename='reserva')
router.register(r'usuarios', UsuarioViewSet)
router.register(r'fichafisica', FichaFisicaViewSet, basename='fichafisica')
router.register(r'ejercicios', EjercicioCatalogoViewSet)
router.register(r'planes', PlanEntrenamientoViewSet, basename='plan')
router.register(r'detallerutina', DetalleRutinaViewSet)

urlpatterns = [
    path('token/', LoginView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', RefreshView.as_view(), name='token_refresh'),
    path('token/logout/', LogoutView.as_view(), name='token_logout'),
    path('configuracion/', ConfiguracionView.as_view(), name='configuracion'),
    path('', include(router.urls)),
]
