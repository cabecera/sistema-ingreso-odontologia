# ============================================
# REQ-10: límites de los campos del registro de paciente
# --------------------------------------------
# Nombre (letras, espacios, guion; 3-100), correo (formato y máx. 150), fecha de
# nacimiento (entre hace 120 y hace 18 años), RUT (módulo 11), teléfono chileno,
# contraseña (10-50, mayúscula, minúscula, número y símbolo) y que las entradas
# con SQL o HTML se rechacen o se traten como texto. Las peticiones usan secure=True.
# ============================================

from datetime import date

from django.test import TestCase

from pacientes.forms import RegistroPacienteForm
from pacientes.models import PerfilPaciente
from pacientes.validators import _hace_anios

CLAVE = "Clave-Segura#2026x"


def datos(**cambios):
    base = {
        "nombre_completo": "María José Pérez", "correo": "maria@example.com",
        "fecha_nacimiento": "1990-01-01", "rut": "12.345.678-5",
        "telefono": "+56 9 1234 5678", "password1": CLAVE, "password2": CLAVE,
    }
    base.update(cambios)
    return base


def errores(**cambios):
    return RegistroPacienteForm(datos(**cambios)).errors


class NombreTests(TestCase):
    def test_acepta_letras_tildes_enie_espacios_y_guion(self):
        for ok in ("Ana", "José Ñandú", "María-José Núñez", "Ibáñez Güemes"):
            with self.subTest(nombre=ok):
                self.assertNotIn("nombre_completo", errores(nombre_completo=ok))

    def test_rechaza_numeros_simbolos_html_y_apostrofe(self):
        for malo in ("Juan 123", "Ana@Perez", "Ana#", "<script>alert(1)</script>", "<b>Ana</b>",
                     "Ana; DROP TABLE x", "O'Higgins", "Ana.", "Ana_Perez"):
            with self.subTest(nombre=malo):
                self.assertIn("nombre_completo", errores(nombre_completo=malo))

    def test_largo_entre_3_y_100(self):
        self.assertIn("nombre_completo", errores(nombre_completo="Al"))
        self.assertNotIn("nombre_completo", errores(nombre_completo="Ana"))
        self.assertNotIn("nombre_completo", errores(nombre_completo="a" * 100))
        self.assertIn("nombre_completo", errores(nombre_completo="a" * 101))


class CorreoTests(TestCase):
    def test_formato_y_largo_maximo(self):
        for malo in ("sin-arroba", "a@b", "a@@b.cl", "a b@example.com", "a@example.com\nBcc: x@y.cl",
                     "a" * 140 + "@example.com"):
            with self.subTest(correo=malo):
                self.assertIn("correo", errores(correo=malo))
        self.assertNotIn("correo", errores(correo="a" * 100 + "@example.com"))


class FechaTests(TestCase):
    def test_limites_120_anios_y_mayor_de_edad(self):
        hoy = date.today()
        casos = {
            "1800-01-01": False,
            (_hace_anios(120)).isoformat(): True,
            (_hace_anios(121)).isoformat(): False,
            (_hace_anios(18)).isoformat(): True,
            hoy.isoformat(): False,
            "2999-01-01": False,
        }
        for valor, valido in casos.items():
            with self.subTest(fecha=valor):
                self.assertEqual("fecha_nacimiento" not in errores(fecha_nacimiento=valor), valido)

    def test_el_menor_de_18_ve_un_mensaje_claro(self):
        menor = _hace_anios(17).isoformat()
        self.assertIn("mayor de 18", str(errores(fecha_nacimiento=menor)["fecha_nacimiento"]))

    def test_el_calendario_limita_el_rango(self):
        attrs = RegistroPacienteForm().fields["fecha_nacimiento"].widget.attrs
        self.assertEqual(attrs["min"], _hace_anios(120).isoformat())
        self.assertEqual(attrs["max"], _hace_anios(18).isoformat())


class RutTests(TestCase):
    def test_modulo_11(self):
        for ok in ("12.345.678-5", "12345678-5", "1.000.005-K".replace("1.000.005-K", "10000013-K"), "7654321-6"):
            with self.subTest(rut=ok):
                self.assertNotIn("rut", errores(rut=ok))
        for malo in ("12.345.678-9", "1234567-0", "123456789012-3", "abcdefgh-1", "12.345.678", "1-9"):
            with self.subTest(rut=malo):
                self.assertIn("rut", errores(rut=malo))


class TelefonoTests(TestCase):
    def test_solo_numeros_mas_inicial_y_espacios(self):
        for ok in ("+56 9 1234 5678", "+56912345678", "9 1234 5678", "912345678"):
            with self.subTest(tel=ok):
                self.assertNotIn("telefono", errores(telefono=ok))
        for malo in ("abc912345678", "+56 9 1234 567a", "9 1234-5678", "(9) 12345678", "91234",
                     "+56 9 1234 56789", "5+6912345678", "+56 9 1234 5678 99"):
            with self.subTest(tel=malo):
                self.assertIn("telefono", errores(telefono=malo))


class ContrasenaTests(TestCase):
    def test_politica(self):
        for malo in ("Ab1!", "Abcdef1!", "abcdefghij1!", "ABCDEFGHIJ1!", "Abcdefghij!!",
                     "Abcdefghij12", "1234567890", "123456", "A1!" + "a" * 60):
            with self.subTest(clave=malo[:12]):
                self.assertIn("password1", errores(password1=malo, password2=malo))
        self.assertNotIn("password1", errores())

    def test_largo_maximo_50(self):
        larga = "Aa1!" + "x" * 46  # 50
        self.assertNotIn("password1", errores(password1=larga, password2=larga))
        mas = larga + "x"
        self.assertIn("password1", errores(password1=mas, password2=mas))


class EntradasPeligrosasTests(TestCase):
    def test_sql_y_html_en_todos_los_campos_no_crean_nada(self):
        carga = "'; DROP TABLE auth_user; --"
        for campo in ("nombre_completo", "correo", "rut", "telefono", "fecha_nacimiento"):
            with self.subTest(campo=campo):
                r = self.client.post("/registro/", datos(**{campo: carga}), secure=True)
                self.assertEqual(r.status_code, 200)  # vuelve al formulario con errores
        self.assertEqual(PerfilPaciente.objects.count(), 0)

    def test_registro_valido_sigue_funcionando(self):
        r = self.client.post("/registro/", datos(), secure=True)
        self.assertRedirects(r, "/registro/enviado/", fetch_redirect_response=False)
