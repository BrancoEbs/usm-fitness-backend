# Gimnasio USM — Backend (API REST)

API del sistema de reservas del gimnasio de la USM. Django 5.2 LTS + Django REST Framework, autenticación JWT.

## Requisitos

- Python 3.10 o superior
- PostgreSQL 14+ en producción (SQLite solo para desarrollo)

## Desarrollo local

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
echo "DJANGO_DEBUG=True" > .env
python manage.py migrate
python manage.py createsuperuser   # luego asignar rol = 3 (Administrador) en /admin/
python manage.py runserver
```

- API: `http://localhost:8000/api/`
- Panel de administración: `http://localhost:8000/admin/`
- Documentación Swagger (solo con `DJANGO_DEBUG=True` o `SWAGGER_ENABLED=True`): `http://localhost:8000/swagger/`

## Pruebas

```bash
DJANGO_DEBUG=True python manage.py test gimnasio
```

Cubren permisos por rol, registro (RUT, correo institucional, contraseña), límites de intentos de login, cierre de sesión, reservas (aforo, sobrecupo, gimnasio cerrado), ficha física y carga de PDF.

## Configuración

Toda la configuración sensible se lee desde variables de entorno o un archivo `.env` (no versionado). Ver `.env.example` para la lista completa. En producción son obligatorias `DJANGO_SECRET_KEY` y `DJANGO_ALLOWED_HOSTS`; con `DJANGO_DEBUG=False` el servidor no arranca sin clave secreta.

Antes de desplegar, verificar con:

```bash
python manage.py check --deploy
```

## Documentación

La documentación técnica (arquitectura, referencia de la API y guía de despliegue) se entrega por separado.
