# Task 59: gestión de usuarios (REQ-14). Solo el Super Administrador.
from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from seguridad.models import BitacoraAuditoria

CLAVE = "Clave-de-prueba-9271"


class GestionUsuariosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for nombre in ("Coordinador", "Estudiante", "Super Administrador"):
            Group.objects.get_or_create(name=nombre)
        cls.admin = User.objects.create_user("admin_rol")
        cls.admin.groups.add(Group.objects.get(name="Super Administrador"))
        cls.coordinador = User.objects.create_user("coord_rol")
        cls.coordinador.groups.add(Group.objects.get(name="Coordinador"))
        cls.estudiante = User.objects.create_user("est_rol")
        cls.estudiante.groups.add(Group.objects.get(name="Estudiante"))
        cls.superuser = User.objects.create_superuser("su_rol", "su@example.com")
        cls.url_lista = reverse("administracion:usuarios")
        cls.url_nuevo = reverse("administracion:usuario_nuevo")

    def _get(self, url, usuario=None):
        if usuario is not None:
            self.client.force_login(usuario)
        return self.client.get(url, secure=True)

    def _datos(self, **cambios):
        datos = {
            "username": "nuevo_estudiante",
            "first_name": "Nora",
            "last_name": "Prueba",
            "email": "nora@example.com",
            "password1": CLAVE,
            "password2": CLAVE,
            "rol": "Estudiante",
        }
        datos.update(cambios)
        return datos

    # ---------- RBAC ----------

    def test_anonimo_es_redirigido_al_login(self):
        for url in (self.url_lista, self.url_nuevo):
            with self.subTest(url=url):
                respuesta = self._get(url)
                self.assertEqual(respuesta.status_code, 302)
                self.assertTrue(respuesta.url.startswith("/login/"))

    def test_otros_roles_reciben_403(self):
        for usuario in (self.coordinador, self.estudiante):
            for url in (self.url_lista, self.url_nuevo):
                with self.subTest(usuario=usuario.username, url=url):
                    self.assertEqual(self._get(url, usuario).status_code, 403)

    def test_otros_roles_no_pueden_crear_ni_cambiar_estado(self):
        self.client.force_login(self.coordinador)
        respuesta = self.client.post(self.url_nuevo, self._datos(), secure=True)
        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(User.objects.filter(username="nuevo_estudiante").exists())
        url = reverse("administracion:usuario_cambiar_estado", args=[self.estudiante.pk])
        self.assertEqual(self.client.post(url, secure=True).status_code, 403)
        self.estudiante.refresh_from_db()
        self.assertTrue(self.estudiante.is_active)

    def test_super_administrador_ve_la_lista(self):
        respuesta = self._get(self.url_lista, self.admin)
        self.assertContains(respuesta, "coord_rol")
        self.assertContains(respuesta, "est_rol")

    # ---------- Crear ----------

    def test_crea_usuario_con_rol_y_sin_privilegios_extra(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(self.url_nuevo, self._datos(), secure=True)
        self.assertEqual(respuesta.status_code, 302)
        nuevo = User.objects.get(username="nuevo_estudiante")
        self.assertEqual([g.name for g in nuevo.groups.all()], ["Estudiante"])
        self.assertFalse(nuevo.is_staff)
        self.assertFalse(nuevo.is_superuser)
        self.assertTrue(nuevo.is_active)

    def test_la_clave_se_guarda_con_hash(self):
        self.client.force_login(self.admin)
        self.client.post(self.url_nuevo, self._datos(), secure=True)
        nuevo = User.objects.get(username="nuevo_estudiante")
        self.assertNotEqual(nuevo.password, CLAVE)
        self.assertTrue(nuevo.check_password(CLAVE))

    def test_rechaza_rol_fuera_de_la_lista(self):
        self.client.force_login(self.admin)
        for rol in ("Paciente", "", "Coordinador' OR '1'='1"):
            with self.subTest(rol=rol):
                respuesta = self.client.post(
                    self.url_nuevo, self._datos(rol=rol), secure=True
                )
                self.assertEqual(respuesta.status_code, 200)
                self.assertFalse(
                    User.objects.filter(username="nuevo_estudiante").exists()
                )

    def test_rechaza_clave_debil_o_distinta(self):
        self.client.force_login(self.admin)
        for p1, p2 in (("12345678", "12345678"), ("corta", "corta"), (CLAVE, CLAVE + "x")):
            with self.subTest(p1=p1, p2=p2):
                respuesta = self.client.post(
                    self.url_nuevo,
                    self._datos(password1=p1, password2=p2),
                    secure=True,
                )
                self.assertEqual(respuesta.status_code, 200)
                self.assertFalse(
                    User.objects.filter(username="nuevo_estudiante").exists()
                )

    def test_rechaza_usuario_repetido(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(
            self.url_nuevo, self._datos(username="coord_rol"), secure=True
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(User.objects.filter(username="coord_rol").count(), 1)

    def test_crear_usuario_deja_registro_sin_la_clave(self):
        self.client.force_login(self.admin)
        self.client.post(self.url_nuevo, self._datos(), secure=True)
        registro = BitacoraAuditoria.objects.get(accion="Creación de usuario")
        self.assertEqual(registro.usuario, self.admin)
        self.assertIn("nuevo_estudiante", registro.detalles)
        self.assertNotIn(CLAVE, registro.detalles)

    def test_post_sin_token_csrf_es_rechazado(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.admin)
        respuesta = cliente.post(self.url_nuevo, self._datos(), secure=True)
        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(User.objects.filter(username="nuevo_estudiante").exists())

    # ---------- Activar / desactivar ----------

    def _cambiar(self, usuario_objetivo):
        url = reverse("administracion:usuario_cambiar_estado", args=[usuario_objetivo.pk])
        return self.client.post(url, secure=True)

    def test_desactiva_y_reactiva_con_registro(self):
        self.client.force_login(self.admin)
        self._cambiar(self.estudiante)
        self.estudiante.refresh_from_db()
        self.assertFalse(self.estudiante.is_active)
        self._cambiar(self.estudiante)
        self.estudiante.refresh_from_db()
        self.assertTrue(self.estudiante.is_active)
        self.assertEqual(
            list(BitacoraAuditoria.objects.order_by("pk").values_list("accion", flat=True)),
            ["Desactivación de usuario", "Activación de usuario"],
        )

    def test_no_puede_desactivarse_a_si_mismo(self):
        self.client.force_login(self.admin)
        self._cambiar(self.admin)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertEqual(BitacoraAuditoria.objects.count(), 0)

    def test_no_gestiona_superusuarios(self):
        self.client.force_login(self.admin)
        self._cambiar(self.superuser)
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_active)

    def test_cambiar_estado_solo_acepta_post(self):
        self.client.force_login(self.admin)
        url = reverse("administracion:usuario_cambiar_estado", args=[self.estudiante.pk])
        self.assertEqual(self.client.get(url, secure=True).status_code, 405)

    def test_usuario_desactivado_no_puede_iniciar_sesion(self):
        self.estudiante.set_password(CLAVE)
        self.estudiante.is_active = False
        self.estudiante.save()
        self.client.post(
            reverse("seguridad:login"),
            {"username": "est_rol", "password": CLAVE},
            secure=True,
        )
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_usuario_inexistente_devuelve_404(self):
        self.client.force_login(self.admin)
        url = reverse("administracion:usuario_cambiar_estado", args=[999999])
        self.assertEqual(self.client.post(url, secure=True).status_code, 404)


# ============================================
# Task 60: gestión de especialidades (REQ-14). Solo el Super Administrador.
# ============================================
from datetime import date

from administracion.models import Especialidad
from pacientes.models import Solicitud


class GestionEspecialidadesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for nombre in ("Coordinador", "Estudiante", "Super Administrador"):
            Group.objects.get_or_create(name=nombre)
        cls.admin = User.objects.create_user("admin_esp")
        cls.admin.groups.add(Group.objects.get(name="Super Administrador"))
        cls.coordinador = User.objects.create_user("coord_esp")
        cls.coordinador.groups.add(Group.objects.get(name="Coordinador"))
        cls.esp = Especialidad.objects.create(nombre="Zzz Prueba Uno", descripcion="Base")
        cls.url_lista = reverse("administracion:especialidades")
        cls.url_nueva = reverse("administracion:especialidad_nueva")
        cls.url_editar = reverse("administracion:especialidad_editar", args=[cls.esp.pk])
        cls.url_estado = reverse(
            "administracion:especialidad_cambiar_estado", args=[cls.esp.pk]
        )

    def _post(self, url, datos=None, usuario=None):
        self.client.force_login(usuario or self.admin)
        return self.client.post(url, datos or {}, secure=True)

    # ---------- RBAC ----------

    def test_anonimo_es_redirigido_al_login(self):
        for url in (self.url_lista, self.url_nueva, self.url_editar):
            with self.subTest(url=url):
                respuesta = self.client.get(url, secure=True)
                self.assertEqual(respuesta.status_code, 302)
                self.assertTrue(respuesta.url.startswith("/login/"))

    def test_otros_roles_reciben_403_en_todo(self):
        self.client.force_login(self.coordinador)
        for url in (self.url_lista, self.url_nueva, self.url_editar):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url, secure=True).status_code, 403)
        respuesta = self._post(
            self.url_nueva, {"nombre": "Hackeada", "activa": "on"}, self.coordinador
        )
        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(Especialidad.objects.filter(nombre="Hackeada").exists())
        self.assertEqual(self._post(self.url_estado, usuario=self.coordinador).status_code, 403)
        self.esp.refresh_from_db()
        self.assertTrue(self.esp.activa)

    def test_super_administrador_ve_la_lista(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(self.url_lista, secure=True), "Zzz Prueba Uno")

    def test_post_sin_token_csrf_es_rechazado(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.admin)
        respuesta = cliente.post(self.url_nueva, {"nombre": "Sin Token"}, secure=True)
        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(Especialidad.objects.filter(nombre="Sin Token").exists())

    # ---------- Crear / editar ----------

    def test_crea_especialidad_y_deja_registro(self):
        respuesta = self._post(
            self.url_nueva,
            {"nombre": "  Implantología   Oral ", "descripcion": "Implantes", "activa": "on"},
        )
        self.assertEqual(respuesta.status_code, 302)
        nueva = Especialidad.objects.get(nombre="Implantología Oral")
        self.assertTrue(nueva.activa)
        registro = BitacoraAuditoria.objects.get(accion="Creación de especialidad")
        self.assertEqual(registro.usuario, self.admin)
        self.assertIn("Implantología Oral", registro.detalles)

    def test_rechaza_nombres_invalidos(self):
        malos = ["", "ab", "123 Cosas", "<script>alert(1)</script>", "'; DROP TABLE x; --", "a_b_c"]
        for nombre in malos:
            with self.subTest(nombre=nombre):
                respuesta = self._post(self.url_nueva, {"nombre": nombre, "activa": "on"})
                self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Especialidad.objects.filter(nombre__in=malos).count(), 0)
        self.assertEqual(BitacoraAuditoria.objects.count(), 0)

    def test_rechaza_nombre_repetido_sin_importar_mayusculas(self):
        respuesta = self._post(self.url_nueva, {"nombre": "zzz PRUEBA uno", "activa": "on"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Especialidad.objects.filter(nombre__iexact="zzz prueba uno").count(), 1)

    def test_editar_permite_conservar_el_mismo_nombre(self):
        respuesta = self._post(
            self.url_editar,
            {"nombre": "Zzz Prueba Uno", "descripcion": "Nueva descripción", "activa": "on"},
        )
        self.assertEqual(respuesta.status_code, 302)
        self.esp.refresh_from_db()
        self.assertEqual(self.esp.descripcion, "Nueva descripción")
        self.assertTrue(BitacoraAuditoria.objects.filter(accion="Edición de especialidad").exists())

    def test_editar_inexistente_devuelve_404(self):
        self.client.force_login(self.admin)
        url = reverse("administracion:especialidad_editar", args=[999999])
        self.assertEqual(self.client.get(url, secure=True).status_code, 404)

    # ---------- Activar / desactivar ----------

    def test_desactivar_la_oculta_del_formulario_publico(self):
        self._post(self.url_estado)
        self.esp.refresh_from_db()
        self.assertFalse(self.esp.activa)
        self.client.logout()  # el formulario público lo ve un anónimo; el personal va a su panel
        publico = self.client.get("/", secure=True)
        self.assertNotContains(publico, "Zzz Prueba Uno")
        self.client.force_login(self.admin)
        self._post(self.url_estado)
        self.esp.refresh_from_db()
        self.assertTrue(self.esp.activa)
        self.client.logout()
        self.assertContains(self.client.get("/", secure=True), "Zzz Prueba Uno")
        self.assertEqual(
            list(BitacoraAuditoria.objects.order_by("pk").values_list("accion", flat=True)),
            ["Desactivación de especialidad", "Activación de especialidad"],
        )

    def test_desactivar_conserva_las_solicitudes_existentes(self):
        Solicitud.objects.create(
            nombre_completo="Paciente Con Especialidad",
            rut="88888888-8",
            fecha_nacimiento=date(1990, 1, 1),
            telefono="+56912345678",
            motivo_consulta="Dolor",
            especialidad=self.esp,
        )
        self._post(self.url_estado)
        self.assertEqual(Solicitud.objects.filter(especialidad=self.esp).count(), 1)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(self.url_lista, secure=True), "Zzz Prueba Uno")

    def test_cambiar_estado_solo_acepta_post(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url_estado, secure=True).status_code, 405)

    def test_no_existe_ruta_para_borrar(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(
            f"/administracion/especialidades/{self.esp.pk}/borrar/", secure=True
        )
        self.assertEqual(respuesta.status_code, 404)
        self.assertTrue(Especialidad.objects.filter(pk=self.esp.pk).exists())
