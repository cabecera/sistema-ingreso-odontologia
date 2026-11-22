# ============================================
# REQ-10: mismas reglas de entrada en los formularios del personal
# --------------------------------------------
# Crear usuario (nombre, apellido, correo, contraseña), especialidad (descripción)
# y login (largo de contraseña) siguen el mismo estándar que el registro del
# paciente: solo letras en los nombres, correo válido de máximo 150, textos sin
# caracteres de control y largos máximos.
# ============================================

from django.contrib.auth.models import User
from django.test import TestCase

from administracion.forms import DESCRIPCION_MAXIMO, EspecialidadForm, UsuarioNuevoForm
from seguridad.forms import LoginForm

CLAVE = "Clave-Segura#2026x"


def datos(**cambios):
    base = {
        "username": "estudiante1", "first_name": "María José", "last_name": "Núñez-Pérez",
        "email": "maria@example.com", "password1": CLAVE, "password2": CLAVE, "rol": "Estudiante",
    }
    base.update(cambios)
    return base


def errores(**cambios):
    return UsuarioNuevoForm(datos(**cambios)).errors


class UsuarioDelPersonalTests(TestCase):

    def test_un_usuario_valido_se_acepta(self):
        self.assertTrue(UsuarioNuevoForm(datos()).is_valid())

    def test_nombres_solo_letras_espacios_y_guion(self):
        for campo in ("first_name", "last_name"):
            for malo in ("Ana123", "Ana@", "<script>x</script>", "Ana; DROP TABLE x", "A", "O'Neil", "x" * 51):
                with self.subTest(campo=campo, valor=malo[:15]):
                    self.assertIn(campo, errores(**{campo: malo}))
            for ok in ("Ana", "Ñandú", "Pérez-Núñez", "De la Fuente"):
                with self.subTest(campo=campo, valor=ok):
                    self.assertNotIn(campo, errores(**{campo: ok}))

    def test_nombre_y_apellido_son_obligatorios(self):
        for campo in ("first_name", "last_name", "email"):
            with self.subTest(campo=campo):
                self.assertIn(campo, errores(**{campo: ""}))

    def test_correo_formato_largo_y_unico(self):
        for malo in ("sin-arroba", "a@b", "a b@example.com", "a" * 145 + "@example.com",
                     "a@example.com\nBcc: x@y.cl"):
            with self.subTest(correo=malo[:20]):
                self.assertIn("email", errores(email=malo))
        User.objects.create_user("otro_usuario", email="Maria@Example.com", password=CLAVE)
        self.assertIn("email", errores())  # mismo correo, sin importar mayúsculas

    def test_el_correo_se_guarda_en_minusculas(self):
        formulario = UsuarioNuevoForm(datos(email="Maria.Nunez@Example.COM"))
        self.assertTrue(formulario.is_valid(), formulario.errors)
        self.assertEqual(formulario.cleaned_data["email"], "maria.nunez@example.com")

    def test_politica_de_contrasena_igual_que_el_registro(self):
        for malo in ("Ab1!", "abcdefghij1!", "ABCDEFGHIJ1!", "Abcdefghij!!", "Abcdefghij12",
                     "A1!" + "a" * 60):
            with self.subTest(clave=malo[:12]):
                e = errores(password1=malo, password2=malo)
                # Django informa la política en password2 (validación del modelo) o password1 (largo).
                self.assertTrue("password1" in e or "password2" in e)

    def test_las_cuentas_del_personal_nunca_dan_acceso_al_admin_de_django(self):
        formulario = UsuarioNuevoForm(datos(rol="Super Administrador"))
        self.assertTrue(formulario.is_valid(), formulario.errors)
        usuario = formulario.save()
        self.assertFalse(usuario.is_staff or usuario.is_superuser)

    def test_el_rol_solo_acepta_la_lista_cerrada(self):
        for malo in ("Paciente", "admin", "Estudiante; DROP", ""):
            with self.subTest(rol=malo):
                self.assertIn("rol", errores(rol=malo))


class EspecialidadYLoginTests(TestCase):

    def test_la_descripcion_pierde_caracteres_de_control_y_tiene_tope(self):
        f = EspecialidadForm({"nombre": "Esp validacion", "descripcion": "Tratamiento\x1b de\x07 encías", "activa": True})
        self.assertTrue(f.is_valid(), f.errors)
        self.assertEqual(f.cleaned_data["descripcion"], "Tratamiento de encías")
        largo = EspecialidadForm({"nombre": "Esp larga", "descripcion": "x" * (DESCRIPCION_MAXIMO + 1)})
        self.assertIn("descripcion", largo.errors)

    def test_el_nombre_de_especialidad_rechaza_html_y_simbolos(self):
        for malo in ("<b>x</b>", "Esp; DROP", "Esp@", "1Esp", "Es_p"):
            with self.subTest(nombre=malo):
                self.assertIn("nombre", EspecialidadForm({"nombre": malo, "descripcion": ""}).errors)

    def test_login_rechaza_contrasenas_gigantes_antes_de_procesarlas(self):
        f = LoginForm(data={"username": "12.345.678-5", "password": "a" * 5000, "tipo": "paciente"})
        self.assertFalse(f.is_valid())
        self.assertIn("password", f.errors)
