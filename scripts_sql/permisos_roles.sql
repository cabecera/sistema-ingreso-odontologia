-- ============================================
-- Task 39: Definir los permisos de cada usuario en la BD
-- Issue padre: REQ-15 (Seguridad de roles a nivel de motor de BD)
-- --------------------------------------------
-- Segunda capa de seguridad, independiente del RBAC de Django
-- (Task 34/35). Aunque alguien vulnere la aplicación, el motor de
-- MySQL igual bloquea las operaciones que ese usuario no debería
-- poder hacer.
--
-- Se ejecuta UNA vez por entorno (local y luego en Azure cuando
-- esté disponible), a mano en MySQL Workbench. No se aplica con
-- migrate porque el ORM no administra usuarios del motor.
--
-- Principio de mínimo privilegio: cada usuario recibe solo lo
-- que necesita, ni un permiso más.
-- ============================================

USE ingreso_odontologia;

-- --------------------------------------------
-- Usuario: app_estudiante
-- Solo puede LEER solicitudes y especialidades. No puede
-- crear, modificar ni borrar nada — refuerza REQ-06 (el
-- estudiante solo ve, no administra) también a nivel de motor.
-- El RUT y los antecedentes vienen cifrados (Task 31), así que
-- aunque este usuario consulte la tabla, no puede leer esos
-- datos en texto plano sin la clave de la aplicación.
-- --------------------------------------------
CREATE USER IF NOT EXISTS 'app_estudiante'@'%' IDENTIFIED BY 'estudiante2026';

GRANT SELECT ON ingreso_odontologia.pacientes_solicitud TO 'app_estudiante'@'%';
GRANT SELECT ON ingreso_odontologia.administracion_especialidad TO 'app_estudiante'@'%';

-- --------------------------------------------
-- Usuario: app_coordinador
-- Puede leer y actualizar solicitudes (para derivarlas, REQ-05),
-- pero no puede borrarlas ni tocar el catálogo de especialidades
-- (eso es exclusivo del Super Administrador, REQ-14).
-- --------------------------------------------
CREATE USER IF NOT EXISTS 'app_coordinador'@'%' IDENTIFIED BY 'coordinador2026';

GRANT SELECT, UPDATE ON ingreso_odontologia.pacientes_solicitud TO 'app_coordinador'@'%';
GRANT SELECT ON ingreso_odontologia.administracion_especialidad TO 'app_coordinador'@'%';

-- --------------------------------------------
-- Usuario: app_admin
-- Acceso completo, incluyendo el catálogo de especialidades
-- (crearlas/desactivarlas, REQ-14) y gestión de usuarios internos
-- (auth_user, auth_group — tablas propias de Django).
-- --------------------------------------------
CREATE USER IF NOT EXISTS 'app_admin'@'%' IDENTIFIED BY 'admin2026';

GRANT SELECT, INSERT, UPDATE, DELETE ON ingreso_odontologia.pacientes_solicitud TO 'app_admin'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON ingreso_odontologia.administracion_especialidad TO 'app_admin'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON ingreso_odontologia.auth_user TO 'app_admin'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON ingreso_odontologia.auth_group TO 'app_admin'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON ingreso_odontologia.auth_user_groups TO 'app_admin'@'%';

FLUSH PRIVILEGES;