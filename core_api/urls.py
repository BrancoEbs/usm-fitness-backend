from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from rest_framework import permissions

from gimnasio.views import LoginView, RefreshView, LogoutView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('gimnasio.urls')),

    # Alias históricos de login (mismas vistas, con límite de intentos)
    path('api/login/', LoginView.as_view(), name='login'),
    path('api/login/refresh/', RefreshView.as_view(), name='login_refresh'),
    path('api/logout/', LogoutView.as_view(), name='logout'),
]

# Documentación Swagger: solo si SWAGGER_ENABLED (por defecto, solo con DEBUG)
if settings.SWAGGER_ENABLED:
    from drf_yasg.views import get_schema_view
    from drf_yasg import openapi

    schema_view = get_schema_view(
        openapi.Info(
            title="API Gimnasio USM",
            default_version='v1',
            description="Documentación interactiva de los endpoints.",
        ),
        public=True,
        permission_classes=(permissions.AllowAny,),
    )
    urlpatterns.append(
        path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui')
    )
