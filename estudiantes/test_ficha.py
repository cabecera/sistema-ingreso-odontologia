# ============================================
# AB#87 (REQ-18): Ficha clínica, examen previo y reporte del estudiante
# --------------------------------------------
# Comprueba que solo el estudiante asignado completa la ficha, solo con la
# atención REALIZADA, que al guardar la solicitud pasa a TERMINADO y no se
# puede repetir, que el contenido clínico va cifrado y fuera de la bitácora,
# que el Coordinador ve el reporte en solo lectura y que el paciente solo
# ve la especialidad indicada.
# Las peticiones usan secure=True para no depender de DEBUG.
# ============================================

from datetime import date, timedelta

from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import Client, TestCase
from django.utils import timezone

from administracion.models import Especialidad
from pacientes.models import FichaClinica, PerfilPaciente, Solicitud
from seguridad.models import BitacoraAuditoria

CLAVE = "Clave-Segura#2026x"
EXAMEN = "Examen previo: encías inflamadas y caries en molar inferior."
REPORTE = "Se recomienda tratamiento de conducto en el molar afectado."


class FichaClinicaTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        grupos = {n: Group.objects.get_or_create(name=n)[0]
                  for n in ("Estudiante", "Coordinador", "Paciente", "Super Administrador")}
        cls.est = User.objects.create_user("est_ficha", password=CLAVE)
        cls.est.groups.add(grupos["Estudiante"])
        cls.otro_est = User.objects.create_user("otro_est_ficha", password=CLAVE)
        cls.otro_est.groups.add(grupos["Estudiante"])
        cls.coord = User.objects.create_user("coord_ficha", password=CLAVE)
        cls.coord.groups.add(grupos["Coordinador"])
        cls.paciente_user = User.objects.create_user("pac.ficha@example.com", password=CLAVE)
        cls.paciente_user.groups.add(grupos["Paciente"])
        PerfilPaciente.objects.create(
            usuario=cls.paciente_user, nombre_completo="María José Pérez",
            fecha_nacimiento=date(1990, 1, 1), rut="12345678-5",
            telefono="+56 9 1234 5678", estado="ACEPTADO",
        )
        cls.esp = Especialidad.objects.create(nombre="Esp Solicitada (tests ficha)", activa=True)
        cls.esp_nec = Especialidad.objects.create(nombre="Esp Necesaria (tests ficha)", activa=True)
        cls.esp_inactiva = Especialidad.objects.create(nombre="Esp Inactiva (tests ficha)", activa=False)

    def crear_solicitud(self, estado="REALIZADO", estudiante=None, paciente=None):
        return Solicitud.objects.create(
            nombre_completo="María José Pérez", fecha_nacimiento=date(1990, 1, 1),
            rut="12345678-5", telefono="+56 9 1234 5678",
            motivo_consulta="Dolor de muelas hace una semana", especialidad=self.esp,
            estado=estado, estudiante_asignado=estudiante or self.est,
            paciente=paciente, fecha_atencion=timezone.now() + timedelta(days=1),
        )

    def datos(self, **cambios):
        base = {"examen_previo": EXAMEN, "observaciones": "Paciente colaborador.",
                "especialidad_requerida": self.esp_nec.pk, "reporte": REPORTE}
        base.update(cambios)
        return base

    def url(self, solicitud, nombre="ficha"):
        return f"/estudiantes/pacientes/{solicitud.pk}/{nombre}/"

    def completar(self, objetivo, /, **cambios):
        return self.client.post(self.url(objetivo), self.datos(**cambios), secure=True)

    # ---------- acceso ----------
    def test_anonimo_es_redirigido_al_login(self):
        s = self.crear_solicitud()
        for nombre in ("ficha", "reporte"):
            r = self.client.get(self.url(s, nombre), secure=True)
            self.assertEqual(r.status_code, 302)
            self.assertTrue(r.url.startswith("/login/"))
        r = self.completar(s)
        self.assertEqual(r.status_code, 302)
        self.assertFalse(FichaClinica.objects.exists())

    def test_otros_roles_reciben_403(self):
        s = self.crear_solicitud()
        for usuario in (self.coord, self.paciente_user):
            self.client.force_login(usuario)
            with self.subTest(usuario=usuario.username):
                self.assertEqual(self.client.get(self.url(s), secure=True).status_code, 403)
                self.assertEqual(self.completar(s).status_code, 403)
                self.assertEqual(self.client.get(self.url(s, "reporte"), secure=True).status_code, 403)
        self.assertFalse(FichaClinica.objects.exists())

    def test_un_estudiante_no_puede_tocar_pacientes_de_otro(self):
        s = self.crear_solicitud(estudiante=self.otro_est)
        self.client.force_login(self.est)
        self.assertEqual(self.client.get(self.url(s), secure=True).status_code, 404)
        self.assertEqual(self.completar(s).status_code, 404)
        self.assertEqual(self.client.get(self.url(s, "reporte"), secure=True).status_code, 404)
        s.refresh_from_db()
        self.assertEqual(s.estado, "REALIZADO")
        self.assertFalse(FichaClinica.objects.exists())

    def test_solicitud_inexistente_da_404(self):
        self.client.force_login(self.est)
        self.assertEqual(self.client.get("/estudiantes/pacientes/99999/ficha/", secure=True).status_code, 404)

    # ---------- reglas de estado ----------
    def test_solo_se_completa_con_la_atencion_realizada(self):
        self.client.force_login(self.est)
        for estado in ("PENDIENTE", "DERIVADA"):
            s = self.crear_solicitud(estado=estado)
            with self.subTest(estado=estado):
                r = self.client.get(self.url(s), secure=True)
                self.assertRedirects(r, "/estudiantes/mis-pacientes/", fetch_redirect_response=False)
                r = self.completar(s)
                self.assertRedirects(r, "/estudiantes/mis-pacientes/", fetch_redirect_response=False)
                s.refresh_from_db()
                self.assertEqual(s.estado, estado)
        self.assertFalse(FichaClinica.objects.exists())

    def test_formulario_se_muestra_con_la_atencion_realizada(self):
        s = self.crear_solicitud()
        self.client.force_login(self.est)
        r = self.client.get(self.url(s), secure=True)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Examen previo")
        self.assertContains(r, "Esp Necesaria (tests ficha)")
        self.assertNotContains(r, "Esp Inactiva (tests ficha)")
        cuerpo = r.content.decode()
        self.assertLess(cuerpo.index('name="examen_previo"'), cuerpo.index('name="especialidad_requerida"'))

    def test_guardar_crea_la_ficha_y_termina_la_solicitud(self):
        s = self.crear_solicitud()
        self.client.force_login(self.est)
        r = self.completar(s)
        self.assertRedirects(r, self.url(s, "reporte"), fetch_redirect_response=False)
        s.refresh_from_db()
        self.assertEqual(s.estado, "TERMINADO")
        ficha = s.ficha
        self.assertEqual(ficha.estudiante, self.est)
        self.assertEqual(ficha.especialidad_requerida, self.esp_nec)
        self.assertEqual(ficha.examen_previo, EXAMEN)
        self.assertEqual(ficha.reporte, REPORTE)

    def test_no_se_puede_completar_dos_veces(self):
        s = self.crear_solicitud()
        self.client.force_login(self.est)
        self.completar(s)
        r = self.completar(s, reporte="Intento de cambiar el reporte ya guardado.")
        self.assertRedirects(r, self.url(s, "reporte"), fetch_redirect_response=False)
        self.assertEqual(FichaClinica.objects.count(), 1)
        self.assertEqual(FichaClinica.objects.get().reporte, REPORTE)
        r = self.client.get(self.url(s), secure=True)
        self.assertRedirects(r, self.url(s, "reporte"), fetch_redirect_response=False)

    # ---------- validaciones ----------
    def test_datos_invalidos_no_guardan_nada(self):
        s = self.crear_solicitud()
        self.client.force_login(self.est)
        casos = {
            "examen vacío": {"examen_previo": ""},
            "examen muy corto": {"examen_previo": "ok"},
            "examen solo espacios": {"examen_previo": " " * 30},
            "reporte muy corto": {"reporte": "listo"},
            "sin especialidad": {"especialidad_requerida": ""},
            "especialidad inexistente": {"especialidad_requerida": 99999},
            "especialidad inactiva": {"especialidad_requerida": self.esp_inactiva.pk},
            "examen demasiado largo": {"examen_previo": "a" * 2001},
            "reporte demasiado largo": {"reporte": "a" * 2001},
            "observaciones demasiado largas": {"observaciones": "a" * 2001},
        }
        for nombre, cambios in casos.items():
            with self.subTest(caso=nombre):
                r = self.completar(s, **cambios)
                self.assertEqual(r.status_code, 200)
        s.refresh_from_db()
        self.assertEqual(s.estado, "REALIZADO")
        self.assertFalse(FichaClinica.objects.exists())

    def test_se_quitan_caracteres_de_control(self):
        s = self.crear_solicitud()
        self.client.force_login(self.est)
        # El carácter nulo lo rechaza Django; los demás de control se eliminan.
        r = self.completar(s, examen_previo="Examen\x00 previo con detalle suficiente.")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(FichaClinica.objects.exists())
        self.completar(s, examen_previo="Examen\x07 previo\x0b completo con detalle suficiente.")
        self.assertNotIn("\x07", s.ficha.examen_previo)
        self.assertNotIn("\x0b", s.ficha.examen_previo)

    def test_campos_extra_del_navegador_se_ignoran(self):
        s = self.crear_solicitud()
        otra = self.crear_solicitud(estudiante=self.otro_est)
        self.client.force_login(self.est)
        self.completar(s, solicitud=otra.pk, estudiante=self.otro_est.pk, estado="PENDIENTE")
        ficha = FichaClinica.objects.get()
        self.assertEqual(ficha.solicitud, s)
        self.assertEqual(ficha.estudiante, self.est)
        otra.refresh_from_db()
        self.assertEqual(otra.estado, "REALIZADO")

    def test_sin_csrf_se_rechaza(self):
        s = self.crear_solicitud()
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.est)
        r = cliente.post(self.url(s), self.datos(), secure=True)
        self.assertEqual(r.status_code, 403)
        self.assertFalse(FichaClinica.objects.exists())

    # ---------- confidencialidad ----------
    def test_el_contenido_clinico_se_guarda_cifrado(self):
        s = self.crear_solicitud()
        self.client.force_login(self.est)
        self.completar(s)
        with connection.cursor() as cursor:
            cursor.execute("SELECT examen_previo, observaciones, reporte FROM pacientes_fichaclinica")
            fila = cursor.fetchone()
        for crudo in fila:
            self.assertNotIn("encías", crudo)
            self.assertNotIn("conducto", crudo)
            self.assertNotIn("colaborador", crudo)

    def test_la_bitacora_no_guarda_contenido_clinico(self):
        s = self.crear_solicitud()
        self.client.force_login(self.est)
        self.completar(s)
        registro = BitacoraAuditoria.objects.get(accion="Ficha clínica completada")
        texto = f"{registro.accion} {registro.detalles}".lower()
        for dato in ("encías", "conducto", "pérez", "12345678", "caries"):
            self.assertNotIn(dato, texto)

    def test_el_reporte_escapa_html(self):
        s = self.crear_solicitud()
        self.client.force_login(self.est)
        self.completar(s, reporte="<script>alert(1)</script> reporte con texto suficiente")
        r = self.client.get(self.url(s, "reporte"), secure=True)
        self.assertNotContains(r, "<script>alert(1)</script>")
        self.assertContains(r, "&lt;script&gt;")

    # ---------- ver el reporte ----------
    def test_el_estudiante_ve_su_reporte(self):
        s = self.crear_solicitud()
        self.client.force_login(self.est)
        self.completar(s)
        r = self.client.get(self.url(s, "reporte"), secure=True)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, REPORTE)
        self.assertContains(r, "Esp Necesaria (tests ficha)")

    def test_el_reporte_no_existe_antes_de_terminar(self):
        s = self.crear_solicitud()
        self.client.force_login(self.est)
        self.assertEqual(self.client.get(self.url(s, "reporte"), secure=True).status_code, 404)

    def test_mis_pacientes_muestra_la_accion_segun_el_estado(self):
        realizado = self.crear_solicitud(estado="REALIZADO")
        self.client.force_login(self.est)
        r = self.client.get("/estudiantes/mis-pacientes/", secure=True)
        self.assertContains(r, "Completar ficha")
        self.assertContains(r, self.url(realizado))
        self.completar(realizado)
        r = self.client.get("/estudiantes/mis-pacientes/", secure=True)
        self.assertContains(r, "Ver reporte")
        self.assertNotContains(r, "Completar ficha")

    # ---------- Coordinador ----------
    def test_el_coordinador_ve_el_reporte_terminado_en_solo_lectura(self):
        s = self.crear_solicitud()
        self.client.force_login(self.est)
        self.completar(s)
        self.client.force_login(self.coord)
        url = f"/coordinacion/solicitudes/{s.pk}/reporte/"
        r = self.client.get(url, secure=True)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, REPORTE)
        self.assertEqual(self.client.post(url, {}, secure=True).status_code, 200)  # POST no modifica nada
        self.assertEqual(FichaClinica.objects.count(), 1)
        listado = self.client.get("/coordinacion/listado/", secure=True)
        self.assertContains(listado, url)

    def test_el_coordinador_no_ve_reportes_de_solicitudes_sin_terminar(self):
        s = self.crear_solicitud()
        self.client.force_login(self.coord)
        self.assertEqual(self.client.get(f"/coordinacion/solicitudes/{s.pk}/reporte/", secure=True).status_code, 404)

    def test_estudiante_paciente_y_anonimo_no_usan_la_ruta_del_coordinador(self):
        s = self.crear_solicitud()
        self.client.force_login(self.est)
        self.completar(s)
        url = f"/coordinacion/solicitudes/{s.pk}/reporte/"
        for usuario in (self.est, self.paciente_user):
            self.client.force_login(usuario)
            with self.subTest(usuario=usuario.username):
                self.assertEqual(self.client.get(url, secure=True).status_code, 403)
        self.client.logout()
        r = self.client.get(url, secure=True)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.url.startswith("/login/"))

    # ---------- Paciente ----------
    def test_el_paciente_ve_solo_la_especialidad_indicada(self):
        s = self.crear_solicitud(paciente=self.paciente_user)
        self.client.force_login(self.est)
        self.completar(s)
        self.client.force_login(self.paciente_user)
        r = self.client.get("/mis-solicitudes/", secure=True)
        self.assertContains(r, "Especialidad indicada: Esp Necesaria (tests ficha)")
        self.assertNotContains(r, REPORTE)
        self.assertNotContains(r, EXAMEN)

    def test_mis_solicitudes_sigue_funcionando_sin_ficha(self):
        self.crear_solicitud(estado="DERIVADA", paciente=self.paciente_user)
        self.client.force_login(self.paciente_user)
        r = self.client.get("/mis-solicitudes/", secure=True)
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Especialidad indicada")
