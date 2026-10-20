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

## Despliegue (CI/CD)

Flujo (todo con planes gratuitos; no hay suscripción de Azure):

```
push / merge a main
        ↓
Azure Pipelines (stage CI: tests, Bandit, pip-audit, docker build)
        ↓
Azure Pipelines (stage CD, solo si CI pasó y la rama es main)
        ↓
POST al Deploy Hook de Render (variable secreta RENDER_DEPLOY_HOOK)
        ↓
Render reconstruye el Web Service (Docker) y sirve gunicorn + WhiteNoise
        ↓
MySQL en Aiven (conexión SSL; el CA vive en certs/aiven-ca.pem)
```

El archivo `certs/aiven-ca.pem` lo agrega el equipo: es el certificado público CA descargado desde la consola de Aiven. No se inventa ni se genera en el repo.

### Variables de entorno

| Variable | Uso |
|---|---|
| `SECRET_KEY` | Clave secreta de Django |
| `DEBUG` | `False` en producción; `True` en CI/tests |
| `ALLOWED_HOSTS` | Hosts permitidos (lista separada por comas) |
| `CSRF_TRUSTED_ORIGINS` | Orígenes CSRF (lista, con esquema `https://`) |
| `RENDER_EXTERNAL_HOSTNAME` | La inyecta Render; se suma a hosts/CSRF |
| `DB_NAME` | Nombre de la base MySQL (Aiven) |
| `DB_USER` | Usuario MySQL |
| `DB_PASSWORD` | Contraseña MySQL |
| `DB_HOST` | Host MySQL |
| `DB_PORT` | Puerto MySQL |
| `DB_SSL_CA` | Ruta al CA de Aiven (p. ej. `certs/aiven-ca.pem`) |
| `FIELD_ENCRYPTION_KEY` | Llave Fernet para campos cifrados |
| `USE_SQLITE` | `True` solo en CI/tests; `False` en producción |

Los valores reales viven en Render y en el `.env` local. No van en el repositorio. El Deploy Hook de Render se configura como variable secreta `RENDER_DEPLOY_HOOK` en Azure Pipelines, no en el YAML.

### Cómo correr los tests

```
USE_SQLITE=True python manage.py test
```

En CI además se define `DEBUG=True` para que `SECURE_SSL_REDIRECT` no rompa el cliente de pruebas.

### Limitación del plan gratuito

El Web Service Free de Render se duerme tras **15 minutos de inactividad**. La primera petición siguiente puede tardar en responder mientras el servicio despierta.

En Azure Pipelines hay que desactivar Auto-Deploy de Render (el CD lo dispara el pipeline) y crear el environment `produccion` la primera vez que corra el stage CD.
