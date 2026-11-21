# ============================================
# AB#82 (REQ-17): Registro de paciente con cuenta pendiente
# --------------------------------------------
# Comprueba que el registro crea una cuenta INACTIVA, que no se puede
# iniciar sesión hasta ser aceptada, que no revela correos ya registrados,
# que la contraseña se valida y se guarda con hash, que el RUT queda
# cifrado y que la bitácora no guarda datos personales.
# Las peticiones usan secure=True para no depender de DEBUG.
# ============================================

from django.contrib.auth.models import Group, User
from django.core import mail
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from pacientes.models import PerfilPaciente
from seguridad.models import BitacoraAuditoria

CLAVE = "Clave-Segura#2026x"
CORREO = "paciente.prueba@example.com"


def datos(**cambios):
    base = {
        "nombre_completo": "María José Pérez",
        "correo": CORREO,
        "fecha_nacimiento": "1990-01-01",
        "rut": "12.345.678-5",
        "telefono": "+56 9 1234 5678",
        "password1": CLAVE,
        "password2": CLAVE,
    }
    base.update(cambios)
    return base


class RegistroPacienteTests(TestCase):
    url = "/registro/"

    def enviar(self, **cambios):
        return self.client.post(self.url, datos(**cambios), secure=True)

    def test_get_muestra_el_formulario_sin_sesion(self):
        r = self.client.get(self.url, secure=True)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Registro de paciente")

    def test_registro_valido_crea_cuenta_inactiva_en_grupo_paciente(self):
        r = self.enviar()
        self.assertRedirects(
            r, reverse("pacientes:registro_enviado"), fetch_redirect_response=False
        )
        usuario = User.objects.get(email=CORREO)
        self.assertFalse(usuario.is_active)
        self.assertFalse(usuario.is_staff)
        self.assertFalse(usuario.is_superuser)
        self.assertEqual(list(usuario.groups.values_list("name", flat=True)), ["Paciente"])
        perfil = usuario.perfil_paciente
        self.assertEqual(perfil.estado, PerfilPaciente.Estado.PENDIENTE)
        self.assertEqual(perfil.rut, "12345678-5")

    def test_correo_se_guarda_en_minusculas(self):
        self.enviar(correo="  Paciente.PRUEBA@Example.com ")
        self.assertTrue(User.objects.filter(email=CORREO).exists())

    def test_la_contrasena_se_guarda_con_hash(self):
        self.enviar()
        usuario = User.objects.get(email=CORREO)
        self.assertNotEqual(usuario.password, CLAVE)
        self.assertNotIn(CLAVE, usuario.password)
        self.assertTrue(usuario.check_password(CLAVE))

    def test_cuenta_pendiente_no_puede_iniciar_sesion(self):
        self.enviar()
        entro = self.client.login(username=CORREO, password=CLAVE)
        self.assertFalse(entro)
        r = self.client.post(
            "/login/", {"username": "12.345.678-5", "password": CLAVE}, secure=True
        )
        self.assertEqual(r.status_code, 200)  # vuelve al login, sin sesión
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_cuenta_pendiente_no_accede_a_paginas_del_personal(self):
        self.enviar()
        usuario = User.objects.get(email=CORREO)
        usuario.is_active = True  # aun aceptada, el rol Paciente no abre estas páginas
        usuario.save()
        self.client.force_login(usuario)
        for url in ("/administracion/", "/coordinacion/", "/estudiantes/pacientes/"):
            with self.subTest(url=url):
                r = self.client.get(url, secure=True)
                self.assertIn(r.status_code, (403, 404))

    def test_envia_aviso_de_correo_sin_contrasena(self):
        self.enviar()
        self.assertEqual(len(mail.outbox), 1)
        correo = mail.outbox[0]
        self.assertEqual(correo.to, [CORREO])
        self.assertIn("48 horas", correo.body)
        self.assertNotIn(CLAVE, correo.body)
        self.assertNotIn("12345678", correo.body)

    def test_correo_repetido_no_revela_nada_y_no_crea_otra_cuenta(self):
        self.enviar()
        mail.outbox.clear()
        r = self.enviar(nombre_completo="Otra Persona", password1="Otra-Clave#2026y",
                        password2="Otra-Clave#2026y")
        # Misma respuesta que un registro nuevo.
        self.assertRedirects(
            r, reverse("pacientes:registro_enviado"), fetch_redirect_response=False
        )
        self.assertEqual(User.objects.filter(email=CORREO).count(), 1)
        self.assertEqual(PerfilPaciente.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 0)
        # La cuenta original no fue modificada.
        self.assertTrue(User.objects.get(email=CORREO).check_password(CLAVE))

    def test_correo_repetido_ignora_mayusculas(self):
        self.enviar()
        self.enviar(correo=CORREO.upper())
        self.assertEqual(User.objects.count(), 1)

    def test_no_se_puede_pisar_a_un_usuario_del_personal(self):
        User.objects.create_user("coordinador1", email="coordinador@example.com", password="x-Clave#2026z")
        self.enviar(correo="coordinador@example.com")
        self.assertEqual(PerfilPaciente.objects.count(), 0)

    def test_contrasenas_distintas_se_rechazan(self):
        r = self.enviar(password2="Distinta-Clave#2026")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "no coinciden")
        self.assertEqual(User.objects.count(), 0)

    def test_contrasenas_debiles_se_rechazan(self):
        for debil in ("12345678", "password", "corta1", CORREO):
            with self.subTest(clave=debil):
                r = self.enviar(password1=debil, password2=debil)
                self.assertEqual(r.status_code, 200)
                self.assertEqual(User.objects.count(), 0)

    def test_campos_invalidos_se_rechazan(self):
        casos = {
            "rut inválido": {"rut": "11.111.111-2"},
            "nombre con símbolos": {"nombre_completo": "Juan<script>"},
            "nombre corto": {"nombre_completo": "Al"},
            "teléfono con letras": {"telefono": "abc12345678"},
            "correo inválido": {"correo": "no-es-correo"},
            "correo con salto de línea": {"correo": "a@example.com\nBcc: x@example.com"},
            "fecha futura": {"fecha_nacimiento": "2999-01-01"},
            "fecha vacía": {"fecha_nacimiento": ""},
        }
        for nombre, cambios in casos.items():
            with self.subTest(caso=nombre):
                r = self.enviar(**cambios)
                self.assertEqual(r.status_code, 200)
                self.assertEqual(User.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_campos_muy_largos_se_rechazan(self):
        r = self.enviar(correo="a" * 200 + "@example.com")
        self.assertEqual(r.status_code, 200)
        r = self.enviar(password1="A1b#" * 60, password2="A1b#" * 60)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(User.objects.count(), 0)

    def test_no_se_puede_registrar_como_staff_ni_con_otro_rol(self):
        # Campos extra enviados por un atacante deben ignorarse.
        self.enviar(is_staff="on", is_superuser="on", is_active="on", rol="Super Administrador",
                    estado="ACEPTADO")
        usuario = User.objects.get(email=CORREO)
        self.assertFalse(usuario.is_staff)
        self.assertFalse(usuario.is_superuser)
        self.assertFalse(usuario.is_active)
        self.assertEqual(list(usuario.groups.values_list("name", flat=True)), ["Paciente"])
        self.assertEqual(usuario.perfil_paciente.estado, "PENDIENTE")

    def test_sin_csrf_se_rechaza(self):
        from django.test import Client
        cliente = Client(enforce_csrf_checks=True)
        r = cliente.post(self.url, datos(), secure=True)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(User.objects.count(), 0)

    def test_bitacora_no_guarda_datos_personales(self):
        self.enviar()
        registro = BitacoraAuditoria.objects.get(accion="Registro de paciente")
        texto = f"{registro.accion} {registro.detalles}".lower()
        for dato in ("paciente.prueba", "maría", "pérez", "12345678", "1234 5678"):
            self.assertNotIn(dato, texto)

    def test_rut_se_guarda_cifrado_en_la_base(self):
        self.enviar()
        with connection.cursor() as cursor:
            cursor.execute("SELECT rut FROM pacientes_perfilpaciente")
            crudo = cursor.fetchone()[0]
        self.assertNotIn("12345678", crudo)

    def test_pagina_enviada_es_publica_y_avisa_el_plazo_de_48_horas(self):
        r = self.client.get("/registro/enviado/", secure=True)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "48 horas")

    def test_login_enlaza_al_registro(self):
        r = self.client.get("/login/", secure=True)
        self.assertContains(r, 'href="/registro/"')

    def test_metodo_no_permitido(self):
        r = self.client.put(self.url, secure=True)
        self.assertEqual(r.status_code, 405)

    def test_falla_el_correo_pero_el_registro_se_guarda(self):
        from unittest import mock
        with mock.patch("pacientes.views.send_mail", side_effect=OSError("smtp caído")):
            r = self.enviar()
        self.assertEqual(r.status_code, 302)
        self.assertTrue(User.objects.filter(email=CORREO).exists())
