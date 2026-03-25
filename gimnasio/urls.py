from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BloqueHorarioViewSet, ReservaViewSet

router = DefaultRouter()
router.register(r'bloques', BloqueHorarioViewSet)
router.register(r'reservas', ReservaViewSet)

urlpatterns = [
    path('', include(router.urls)),
]