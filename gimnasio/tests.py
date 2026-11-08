"""
Pruebas de seguridad y reglas de negocio de la API.

Ejecutar con:  DJANGO_DEBUG=True python manage.py test gimnasio
"""
from datetime import date, timedelta, time

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from .models import (
    Usuario, Rol, BloqueHorario, Reserva, FichaFisica, PlanEntrenamiento, ConfiguracionGimnasio,
)


def crear_usuario(username, rol=Rol.ALUMNO, **extra):
    return Usuario.objects.create_user(username=username, password='Clave-Segura-2026', rol=rol, **extra)


def bloque_futuro(dias=7, aforo=20):
    fecha = date.today() + timedelta(days=dias)
    return BloqueHorario.objects.create(
        dia='LU', fecha=fecha, codigo_bloque='B3', hora_inicio=time(11, 5), hora_fin=time(12, 15),
        aforo_regular=aforo,
    )


class BaseAPITest(APITestCase):
    def setUp(self):
        cache.clear()  # reinicia contadores de límite de solicitudes
        self.alumno = crear_usuario('11111111-1')
        self.otro_alumno = crear_usuario('22222222-2')
        self.entrenador = crear_usuario('33333333-3', rol=Rol.ENTRENADOR)
        self.admin = crear_usuario('44444444-4', rol=Rol.ADMIN)


class PermisosUsuariosTest(BaseAPITest):
    def test_alumno_no_puede_listar_usuarios(self):
        self.client.force_authenticate(self.alumno)
        self.assertEqual(self.client.get('/api/usuarios/').status_code, 403)

    def test_entrenador_puede_listar_usuarios(self):
        self.client.force_authenticate(self.entrenador)
        self.assertEqual(self.client.get('/api/usuarios/').status_code, 200)

    def test_alumno_no_puede_eliminar_usuarios(self):
        self.client.force_authenticate(self.alumno)
        r = self.client.delete(f'/api/usuarios/{self.otro_alumno.id}/')
        self.assertEqual(r.status_code, 403)
        self.assertTrue(Usuario.objects.filter(id=self.otro_alumno.id).exists())

    def test_entrenador_no_puede_eliminar_ni_crear_usuarios(self):
        self.client.force_authenticate(self.entrenador)
        self.assertEqual(self.client.delete(f'/api/usuarios/{self.alumno.id}/').status_code, 403)
        self.assertEqual(self.client.post('/api/usuarios/', {'username': 'x'}).status_code, 403)

    def test_alumno_no_puede_cambiar_su_rol(self):
        self.client.force_authenticate(self.alumno)
        r = self.client.patch(f'/api/usuarios/{self.alumno.id}/actualizar_permisos/', {'rol': 3}, format='json')
        self.assertEqual(r.status_code, 403)
        self.alumno.refresh_from_db()
        self.assertEqual(self.alumno.rol, Rol.ALUMNO)

    def test_admin_valida_rol(self):
        self.client.force_authenticate(self.admin)
        r = self.client.patch(f'/api/usuarios/{self.alumno.id}/actualizar_permisos/', {'rol': 9}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_admin_no_puede_quitarse_admin(self):
        self.client.force_authenticate(self.admin)
        r = self.client.patch(f'/api/usuarios/{self.admin.id}/actualizar_permisos/', {'rol': 1}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_me_requiere_sesion(self):
        self.assertEqual(self.client.get('/api/usuarios/me/').status_code, 401)


class RegistroTest(BaseAPITest):
    datos = {
        'username': '12.345.678-5', 'password': 'Gimnasio-USM-2026', 'first_name': ' ana ',
        'last_name': 'pérez', 'email': 'ana.perez@sansano.usm.cl', 'carrera': 'ing. civil informática',
    }

    def test_registro_valido_crea_alumno(self):
        r = self.client.post('/api/usuarios/registro/', {**self.datos, 'rol': 3}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        u = Usuario.objects.get(username='12345678-5')
        self.assertEqual(u.rol, Rol.ALUMNO)  # se ignora el rol enviado
        self.assertEqual(u.first_name, 'Ana')
        self.assertNotEqual(u.password, self.datos['password'])

    def test_rut_invalido(self):
        r = self.client.post('/api/usuarios/registro/', {**self.datos, 'username': '12345678-9'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('username', r.data)

    def test_correo_no_institucional(self):
        r = self.client.post('/api/usuarios/registro/', {**self.datos, 'email': 'ana@gmail.com'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('email', r.data)

    def test_contrasena_debil(self):
        r = self.client.post('/api/usuarios/registro/', {**self.datos, 'password': '12345678'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('password', r.data)


class LoginTest(BaseAPITest):
    def test_login_entrega_tokens_y_limita_intentos(self):
        r = self.client.post('/api/token/', {'username': '11111111-1', 'password': 'Clave-Segura-2026'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertIn('access', r.data)
        self.assertIn('refresh', r.data)
        # Límite por defecto: 10 intentos por minuto por IP
        codigos = [self.client.post('/api/token/', {'username': '11111111-1', 'password': 'mala'}, format='json').status_code
                   for _ in range(10)]
        self.assertEqual(codigos[-1], 429)
        self.assertIn(401, codigos)

    def test_logout_invalida_refresh(self):
        tokens = self.client.post('/api/token/', {'username': '11111111-1', 'password': 'Clave-Segura-2026'}, format='json').data
        self.assertEqual(self.client.post('/api/token/logout/', {'refresh': tokens['refresh']}, format='json').status_code, 200)
        r = self.client.post('/api/token/refresh/', {'refresh': tokens['refresh']}, format='json')
        self.assertEqual(r.status_code, 401)


class BloquesTest(BaseAPITest):
    def test_alumno_no_puede_modificar_bloque(self):
        b = bloque_futuro()
        self.client.force_authenticate(self.alumno)
        r = self.client.patch(f'/api/bloques/{b.id}/modificar_bloque/', {'aforo_regular': 999}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_entrenador_modifica_aforo_validado(self):
        b = bloque_futuro(dias=0)  # el staff gestiona los bloques de la semana en curso
        self.client.force_authenticate(self.entrenador)
        self.assertEqual(self.client.patch(f'/api/bloques/{b.id}/modificar_bloque/', {'aforo_regular': 999}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(f'/api/bloques/{b.id}/modificar_bloque/', {'aforo_regular': 15}, format='json').status_code, 200)

    def test_solo_admin_elimina_bloques(self):
        b = bloque_futuro()
        self.client.force_authenticate(self.entrenador)
        self.assertEqual(self.client.delete(f'/api/bloques/{b.id}/').status_code, 403)


class ReservasTest(BaseAPITest):
    def test_reserva_usa_fecha_del_bloque(self):
        b = bloque_futuro()
        self.client.force_authenticate(self.alumno)
        r = self.client.post('/api/reservas/', {'bloque': b.id, 'fecha_especifica': '2020-01-01'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(Reserva.objects.get().fecha_especifica, b.fecha)

    def test_aforo_y_sobrecupo_seleccionado(self):
        b = bloque_futuro(aforo=1)
        self.client.force_authenticate(self.alumno)
        self.assertEqual(self.client.post('/api/reservas/', {'bloque': b.id}, format='json').status_code, 201)
        self.client.force_authenticate(self.otro_alumno)
        self.assertEqual(self.client.post('/api/reservas/', {'bloque': b.id}, format='json').status_code, 400)
        self.otro_alumno.es_seleccionado = True
        self.otro_alumno.save()
        r = self.client.post('/api/reservas/', {'bloque': b.id}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data['es_sobrecupo'])

    def test_no_se_reserva_con_gimnasio_cerrado(self):
        b = bloque_futuro()
        config = ConfiguracionGimnasio.load()
        config.gimnasio_abierto = False
        config.save()
        self.client.force_authenticate(self.alumno)
        self.assertEqual(self.client.post('/api/reservas/', {'bloque': b.id}, format='json').status_code, 400)

    def test_alumno_no_ve_ni_cancela_reservas_ajenas(self):
        b = bloque_futuro()
        reserva = Reserva.objects.create(alumno=self.otro_alumno, bloque=b, fecha_especifica=b.fecha)
        self.client.force_authenticate(self.alumno)
        self.assertEqual(self.client.get('/api/reservas/').data, [])
        self.assertEqual(self.client.post(f'/api/reservas/{reserva.id}/cancelar/').status_code, 404)

    def test_reservas_no_se_editan_ni_borran_directamente(self):
        b = bloque_futuro()
        reserva = Reserva.objects.create(alumno=self.alumno, bloque=b, fecha_especifica=b.fecha)
        self.client.force_authenticate(self.alumno)
        self.assertEqual(self.client.delete(f'/api/reservas/{reserva.id}/').status_code, 405)
        self.assertEqual(self.client.patch(f'/api/reservas/{reserva.id}/', {}, format='json').status_code, 405)

    def test_alumno_no_marca_asistencia(self):
        b = bloque_futuro()
        reserva = Reserva.objects.create(alumno=self.alumno, bloque=b, fecha_especifica=b.fecha)
        self.client.force_authenticate(self.alumno)
        r = self.client.post(f'/api/reservas/{reserva.id}/marcar_asistencia/', {'estado': 'PRE'}, format='json')
        self.assertEqual(r.status_code, 403)


class FichaFisicaTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.ficha = FichaFisica.objects.create(usuario=self.alumno, peso_kg=70, estatura_cm=175)

    def test_alumno_no_escribe_observaciones_del_entrenador(self):
        self.client.force_authenticate(self.alumno)
        r = self.client.patch(f'/api/fichafisica/{self.ficha.id}/', {'observaciones_entrenador': 'falso'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.ficha.refresh_from_db()
        self.assertIsNone(self.ficha.observaciones_entrenador)

    def test_alumno_no_ve_fichas_ajenas(self):
        self.client.force_authenticate(self.otro_alumno)
        self.assertEqual(self.client.get(f'/api/fichafisica/{self.ficha.id}/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/fichafisica/por_alumno/?alumno_id={self.alumno.id}').status_code, 403)

    def test_entrenador_lee_pero_no_edita_medidas(self):
        self.client.force_authenticate(self.entrenador)
        self.assertEqual(self.client.get(f'/api/fichafisica/{self.ficha.id}/').status_code, 200)
        self.assertEqual(self.client.patch(f'/api/fichafisica/{self.ficha.id}/', {'peso_kg': 50}, format='json').status_code, 404)
        r = self.client.patch(f'/api/fichafisica/{self.ficha.id}/actualizar_nota/', {'observaciones_entrenador': 'ok'}, format='json')
        self.assertEqual(r.status_code, 200)

    def test_rangos_de_medidas(self):
        self.client.force_authenticate(self.alumno)
        r = self.client.patch(f'/api/fichafisica/{self.ficha.id}/', {'peso_kg': 900}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_ficha_duplicada(self):
        self.client.force_authenticate(self.alumno)
        r = self.client.post('/api/fichafisica/', {'peso_kg': 70, 'estatura_cm': 170}, format='json')
        self.assertEqual(r.status_code, 400)


class PlanesTest(BaseAPITest):
    def test_alumno_no_crea_planes(self):
        self.client.force_authenticate(self.alumno)
        r = self.client.post('/api/planes/', {'titulo': 'x', 'fecha_vencimiento': str(date.today() + timedelta(days=5))}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_pdf_valido_e_invalido(self):
        self.client.force_authenticate(self.entrenador)
        venc = str(date.today() + timedelta(days=5))
        falso = SimpleUploadedFile('plan.pdf', b'MZ esto no es un pdf', content_type='application/pdf')
        r = self.client.post('/api/planes/', {'titulo': 'x', 'fecha_vencimiento': venc, 'archivo_adjunto': falso}, format='multipart')
        self.assertEqual(r.status_code, 400)

        with self.settings(MEDIA_ROOT=self._tmp()):
            pdf = SimpleUploadedFile('plan.pdf', b'%PDF-1.4 contenido', content_type='application/pdf')
            r = self.client.post('/api/planes/', {'titulo': 'Plan', 'es_global': True, 'fecha_vencimiento': venc,
                                                  'archivo_adjunto': pdf}, format='multipart')
            self.assertEqual(r.status_code, 201, r.data)
            plan_id = r.data['id']
            self.assertEqual(r.data['archivo_url'], f'/api/planes/{plan_id}/archivo/')

            self.client.force_authenticate(self.alumno)
            self.assertEqual(self.client.get(f'/api/planes/{plan_id}/archivo/').status_code, 200)
            self.client.force_authenticate(None)
            self.assertEqual(self.client.get(f'/api/planes/{plan_id}/archivo/').status_code, 401)

    def test_alumno_no_ve_plan_personal_ajeno(self):
        plan = PlanEntrenamiento.objects.create(titulo='p', fecha_vencimiento=date.today() + timedelta(days=3),
                                                alumno_asignado=self.otro_alumno)
        self.client.force_authenticate(self.alumno)
        self.assertEqual(self.client.get(f'/api/planes/{plan.id}/').status_code, 404)

    def _tmp(self):
        import tempfile
        return tempfile.mkdtemp()


class ConfiguracionTest(BaseAPITest):
    def test_solo_admin_cierra_gimnasio(self):
        self.client.force_authenticate(self.entrenador)
        self.assertEqual(self.client.patch('/api/configuracion/', {'gimnasio_abierto': False}, format='json').status_code, 403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.patch('/api/configuracion/', {'gimnasio_abierto': False}, format='json').status_code, 200)
