# sistema-ingreso-odontologia

Prototipo académico de plataforma web segura que digitaliza el ingreso y derivación de solicitudes de atención de pacientes en una facultad de odontología, reemplazando el actual proceso presencial (solo lunes 8:00 AM, sin filtro por especialidad) por un flujo digital, eficiente y seguro bajo el enfoque Security by Design.


## Descripción
 
Los pacientes registran su solicitud de atención mediante un portal web público, indicando su motivo de consulta y la especialidad odontológica requerida. Un Coordinador revisa, filtra, prioriza y deriva formalmente cada solicitud a un Estudiante, quien solo puede ver los casos que le fueron asignados. Un Super Administrador gestiona usuarios, roles y el catálogo de especialidades.

## Problema que resuelve
 
- El ingreso de pacientes actualmente solo se puede solicitar presencialmente, los lunes a las 8:00 AM.
- No existe priorización por urgencia ni filtrado por especialidad.
- La derivación de pacientes a estudiantes es manual y sin trazabilidad.
- No hay protección formal de los datos personales y de salud recopilados.

## Roles del sistema
 
| Rol | Acceso | Descripción |
|---|---|---|
| **Paciente** | Público, sin cuenta | Registra su solicitud de atención |
| **Estudiante** | Autenticado | Ve únicamente los pacientes que le fueron derivados |
| **Coordinador** | Autenticado | Revisa, prioriza y deriva solicitudes |
| **Super Administrador** | Autenticado | Gestiona usuarios, roles y especialidades |

 ## Funcionalidades principales
 
- Registro público de solicitud con selección de especialidad (REQ-01, REQ-02)
- Autenticación y control de acceso basado en roles — RBAC (REQ-03, REQ-07)
- Listado, filtrado y priorización de solicitudes (REQ-04)
- Derivación formal de pacientes a estudiantes (REQ-05, REQ-06)
- Panel de administración de usuarios, roles y especialidades (REQ-14)
- Reportes: listado simple, estadístico con gráfico y con filtros (REQ-12)
- Bitácora de auditoría de solo lectura (REQ-11)

## Equipo
 
| Integrante | Rol |
|---|---|
| Carlos Becerra | *(completar)* |
| Guido Lezano | *(completar)* |
| Paulina Gallardo | *(completar)* |

*Proyecto desarrollado para la asignatura de Desarrollo Seguro de Software (DevSecOps) — INACAP.*
