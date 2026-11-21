# ============================================
# Navegación por rol y destino después de iniciar sesión
# --------------------------------------------
# Cada rol ve en el menú solo los enlaces que le corresponden y TODOS los
# enlaces que ve se pueden abrir (nunca un enlace que termine en 403/404).
# Cada rol aterriza en su página principal al iniciar sesión.
# El menú es solo presentación: la seguridad real sigue en @role_required.
# Las peticiones usan secure=True para no depender de DEBUG.
# ============================================

from django.contrib.auth.models import Group, User
from django.test import TestCase

CLAVE = "Clave-Segura#2026x"

ENLACES = {
    "mis_solicitudes": "/mis-solicitudes/",
    "nueva_solicitud": "/",
    "solicitudes": "/coordinacion/listado/",
    "registros": "/coordinacion/registros/",
    "mis_pacientes": "/estudiantes/mis-pacientes/",
    "usuarios": "/administracion/usuarios/",
    "especialidades": "/administracion/especialidades/",
}
# Enlaces del menú que debe ver cada rol (el resto NO debe aparecer).
ESPERADOS = {
    "Paciente": {"mis_solicitudes"},  # "/" siempre es el logo; "Nueva solicitud" se prueba aparte
    "Coordinador": {"solicitudes", "registros"},
    "Estudiante": {"mis_pacientes"},
    "Super Administrador": {"solicitudes", "registros", "usuarios", "especialidades"},
    "superusuario": {"solicitudes", "registros", "usuarios", "especialidades"},
}
DESTINO_LOGIN = {
    "Paciente": "/mis-solicitudes/",
    "Coordinador": "/coordinacion/",
    "Estudiante": "/estudiantes/mis-pacientes/",
    "Super Administrador": "/administracion/",
    "superusuario": "/administracion/",
}


class NavegacionPorRolTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.usuarios = {}
        for rol in ("Paciente", "Coordinador", "Estudiante", "Super Administrador"):
            grupo = Group.objects.get_or_create(name=rol)[0]
            usuario = User.objects.create_user(f"nav_{rol.replace(' ', '_').lower()}", password=CLAVE)
            usuario.groups.add(grupo)
            cls.usuarios[rol] = usuario
        cls.usuarios["superusuario"] = User.objects.create_superuser("nav_superuser", password=CLAVE)

    def menu(self, rol):
        self.client.force_login(self.usuarios[rol])
        return self.client.get("/", secure=True).content.decode()

    def test_cada_rol_ve_solo_sus_enlaces(self):
        for rol, esperados in ESPERADOS.items():
            html = self.menu(rol)
            for nombre, url in ENLACES.items():
                if nombre == "nueva_solicitud":
                    continue
                with self.subTest(rol=rol, enlace=nombre):
                    visible = f'class="nav-link" href="{url}"' in html
                    self.assertEqual(visible, nombre in esperados)

    def test_todo_enlace_del_menu_se_puede_abrir(self):
        for rol, esperados in ESPERADOS.items():
            self.client.force_login(self.usuarios[rol])
            for nombre in esperados:
                with self.subTest(rol=rol, enlace=nombre):
                    r = self.client.get(ENLACES[nombre], secure=True)
                    self.assertEqual(r.status_code, 200)

    def test_solo_el_paciente_ve_nueva_solicitud_en_el_menu(self):
        marca = 'class="nav-link" href="/">Nueva solicitud'
        self.assertIn(marca, self.menu("Paciente"))
        for rol in ("Coordinador", "Estudiante", "Super Administrador", "superusuario"):
            self.assertNotIn(marca, self.menu(rol))

    def test_el_anonimo_no_ve_enlaces_del_personal(self):
        html = self.client.get("/", secure=True).content.decode()
        for nombre, url in ENLACES.items():
            if nombre != "nueva_solicitud":
                self.assertNotIn(f'class="nav-link" href="{url}"', html)
        self.assertIn("Iniciar sesión", html)

    def test_cada_rol_aterriza_en_su_pagina_al_iniciar_sesion(self):
        for rol, destino in DESTINO_LOGIN.items():
            usuario = self.usuarios[rol]
            with self.subTest(rol=rol):
                self.client.logout()
                r = self.client.post(
                    "/login/", {"username": usuario.username, "password": CLAVE}, secure=True
                )
                self.assertRedirects(r, destino, fetch_redirect_response=False)

    def test_la_pagina_de_destino_abre_sin_error(self):
        for rol, destino in DESTINO_LOGIN.items():
            self.client.force_login(self.usuarios[rol])
            with self.subTest(rol=rol):
                self.assertEqual(self.client.get(destino, secure=True).status_code, 200)

    def test_los_paneles_tienen_enlaces_a_sus_secciones(self):
        self.client.force_login(self.usuarios["Estudiante"])
        self.assertContains(self.client.get("/estudiantes/", secure=True), "/estudiantes/mis-pacientes/")
        self.client.force_login(self.usuarios["Coordinador"])
        r = self.client.get("/coordinacion/", secure=True)
        self.assertContains(r, "/coordinacion/listado/")
        self.assertContains(r, "/coordinacion/registros/")

    def test_ocultar_el_menu_no_da_ni_quita_acceso(self):
        # Un estudiante no ve "Usuarios" y tampoco puede abrirlo.
        self.client.force_login(self.usuarios["Estudiante"])
        self.assertEqual(self.client.get("/administracion/usuarios/", secure=True).status_code, 403)
        self.assertEqual(self.client.get("/coordinacion/registros/", secure=True).status_code, 403)
