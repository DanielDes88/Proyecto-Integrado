# GoClinical Django — portales por usuario

Prototipo académico en Django y SQLite con inicio de sesión y vistas específicas para **paciente, profesional y administrador**, inspirado en los tres mockups de GoClinical adjuntos al proyecto. Los pagos y documentos son simulados.

## Ejecutar en Windows

1. Instala Python 3.12 o 3.13 si no lo tienes.
2. Extrae completamente el ZIP en **una carpeta nueva**. No reemplaces tu base de datos anterior.
3. Ejecuta `INICIAR_WINDOWS.bat`.
4. Abre http://127.0.0.1:8000/.

El archivo BAT crea un entorno virtual, instala las dependencias, aplica las migraciones y prepara las cuentas de prueba. Mantén abierta la terminal. Ctrl+C detiene el servidor. Se requiere internet para la instalación inicial de dependencias.

Alternativa manual desde la carpeta que contiene `manage.py`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py preparar_demo
.\.venv\Scripts\python.exe manage.py runserver
```

No necesitas activar el entorno ni modificar la política de PowerShell. Si `python` no se reconoce, prueba `py` en el primer comando. En Linux/macOS: crea el entorno con `python3 -m venv .venv` y sustituye `.venv\Scripts\python.exe` por `.venv/bin/python`.

## Cuentas de demostración

| Usuario | Contraseña inicial | Portal |
| --- | --- | --- |
| `paciente` | `GoClinical2026!` | Teresa Cortés: servicios, solicitudes, perfil y pagos |
| `profesional` | `GoClinical2026!` | Catalina Hadad: agenda, disponibilidad, perfil y facturación |
| `admin` | `GoClinical2026!` | Cuentas, solicitudes, informes, clientes, pagos y comentarios |

Son credenciales públicas únicamente para una demostración local con datos ficticios. `preparar_demo` crea las cuentas cuando no existen; no restablece sus contraseñas ni elimina sus cambios. Para cambiar de perfil, **cierra sesión** y accede con otra cuenta. Las pestañas ya no permiten saltar libremente entre usuarios.

Las cuentas comparten los registros de un mismo espacio de demostración: una reserva del paciente aparece en la agenda del profesional asignado y en administración. Los datos permanecen en `db.sqlite3` incluso al cerrar sesión. La autorización comprueba tanto el rol como la propiedad/asignación del registro.

## Qué puede hacer cada perfil

### Paciente

- Inicio con servicios y calendario de próximas visitas.
- Catálogo con búsqueda y filtro por categoría.
- Reservar, simular pago aprobado/rechazado y consultar detalle.
- Cancelar visitas confirmadas.
- Evaluar una atención finalizada; el comentario queda pendiente de moderación.
- Ver perfil ficticio, historial de pagos y ayuda.

### Profesional

- Inicio con agenda programada y resumen de prestaciones.
- Ver únicamente las atenciones que tiene asignadas.
- Avanzar Confirmada → En camino → En atención → Finalizada.
- Crear o quitar bloques de disponibilidad, rechazando solapamientos.
- Consultar servicios y su perfil; ver un ejemplo de certificados sin carga de documentos reales.
- Consultar honorarios ilustrativos (70 % del precio histórico) y registrar el envío de una boleta ficticia.

### Administrador

- Consultar resumen, tablas de solicitudes y gráficos calculados desde SQLite.
- Ver cuentas y pacientes del espacio de demostración.
- Aprobar o rechazar postulaciones ficticias.
- Consultar pagos y conteo de boletas ficticias recibidas.
- Aprobar comentarios; solo entonces pueden incluirse en la información disponible para el profesional.

## Recorrido de presentación

1. Ingresa como `paciente` y agenda una atención desde Servicios.
2. Selecciona Pago aprobado; verifica la reserva en Mis solicitudes.
3. Cierra sesión e ingresa como `profesional`.
4. En Agendamiento, avanza la atención hasta Finalizada.
5. Vuelve al paciente y evalúa la visita desde Historial.
6. Accede como `admin` y aprueba el comentario. Revisa el resumen y las tablas.
7. Recarga la página para comprobar persistencia.

## Inspiración en los mockups

- **Paleta** de la página 4 de los tres archivos: `#309dad`, `#4ed1c7`, `#0d8e92`, `#295e80`, `#ff9a2b` y fondos grises claros.
- **Paciente**: Inicio, Servicios, Solicitudes, Mi perfil; calendario, detalle de atención y pagos, basados en las pantallas del PDF del paciente.
- **Profesional**: Agendamiento, configuración de horarios, prestaciones, certificados y facturación, basados en el PDF profesional corregido.
- **Administrador**: menú lateral, resumen de actividad, gestión de cuentas, solicitudes e informes, basados en el PDF de dashboard.
- Adaptación web responsive: el contenido y la barra lateral ocupan columnas independientes; en pantallas pequeñas el menú pasa a una fila desplazable. No se usan imágenes de las pantallas originales como sustituto de botones o formularios.
- Tipografía de sistema Helvetica Neue/Helvetica/Arial; no se distribuyen fuentes comerciales.

La propuesta es una adaptación funcional y simplificada; no reproduce todas las pantallas de los PDFs. No hay login con Google/Apple, mapas reales, chat, notificaciones externas, carga de certificados, reprogramación, visitas recurrentes ni emisión tributaria. Las vistas de certificados y boletas indican expresamente que son ejemplos.

## Panel nativo de Django

El portal `admin` de GoClinical es distinto del panel nativo `/admin/`. La cuenta de muestra `admin` no es un superusuario y no tiene acceso a ese panel.

Para revisar o editar modelos desde el panel nativo:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

Abre http://127.0.0.1:8000/admin/ con la cuenta que acabas de crear. Allí se pueden gestionar servicios y perfiles. Un superusuario sin `UserProfile` administra modelos desde `/admin/`; no accede automáticamente a un portal de negocio. Los perfiles nuevos requieren asignar explícitamente su rol y espacio en el panel nativo.

## Archivos principales

| Archivo | Función |
| --- | --- |
| `clinical/models.py` | Perfiles, usuarios vinculados a atenciones, servicios, disponibilidad y evaluaciones |
| `clinical/demo.py` | Permisos por acción, consultas por propietario/asignación y reglas del negocio |
| `clinical/views.py` | Login/logout, rutas de portales y API |
| `clinical/templates/clinical/login.html` | Pantalla de acceso |
| `clinical/templates/clinical/index.html` | Estructura común del portal |
| `clinical/static/clinical/app.js` | Menús y vistas específicas de cada perfil, formularios y calendarios |
| `clinical/static/clinical/roles.css` | Paleta GoClinical, login y adaptación por tamaño de pantalla |
| `clinical/static/clinical/style.css` | Estilos base y componentes reutilizables |
| `clinical/management/commands/preparar_demo.py` | Cuentas y registros de demostración |
| `clinical/migrations/` | Migraciones completas, incluida la incorporación de roles |
| `clinical/tests.py` | Pruebas de acceso, propiedad, operaciones y flujo entre usuarios |

## Validación y límites

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test clinical
```

Se aplican sesiones Django, contraseñas con hash del framework, CSRF, consultas ORM, restricciones y transacciones. El servidor controla el rol y el objeto aunque se cambie una URL o se envíe manualmente una petición. Hay limitación básica de intentos de login por origen (10 intentos, 5 minutos, caché local); no sustituye una solución distribuida de producción.

La reserva utiliza horarios fijos y rechaza solapamientos entre visitas del espacio de demostración; no calcula disponibilidad a partir de los bloques del profesional. El primer profesional activo del espacio se asigna automáticamente. El alcance está pensado para las tres cuentas iniciales y una presentación local, no para un marketplace con asignación concurrente real.

Las APIs reciben información ficticia y no procesan dinero ni documentos clínicos. SQLite, DEBUG de desarrollo y las credenciales de ejemplo no son una configuración de producción. Para uso real se requieren revisión de seguridad, asignación profesional, infraestructura y reglas de negocio definitivas.

Si actualizas sobre una copia anterior: respalda `db.sqlite3`, ejecuta `migrate` y `preparar_demo`. Los registros anónimos de la versión anterior se conservan en su espacio original; no se asignan automáticamente a las cuentas nuevas. La opción recomendada para esta entrega es extraer en carpeta nueva.

## Solución de errores

- **No such table**: ejecuta `manage.py migrate`.
- **Usuario no válido**: ejecuta `manage.py preparar_demo`; si cambiaste la contraseña usa `manage.py changepassword paciente` (o el usuario correspondiente).
- **Cuenta existente sin perfil**: el comando no se apropia de cuentas existentes. Usa una carpeta nueva o configura explícitamente su UserProfile.
- **No module named django**: ejecuta los comandos con el Python de `.venv`.
- **No se ve el diseño**: entra por http://127.0.0.1:8000/, no abras los HTML directamente. Recarga con Ctrl+F5.
- **Puerto ocupado**: `manage.py runserver 8001` y http://127.0.0.1:8001/.
- **403 al abrir otro portal**: es el comportamiento esperado; cierra sesión y usa una cuenta de ese rol.

Referencias técnicas: documentación oficial de Django 5.2 sobre autenticación, permisos, sesiones y CSRF. Referencias visuales: los tres PDFs de mockups proporcionados por GoClinical.

## Página pública

La ruta `/` muestra la presentación pública de GoClinical, el catálogo de servicios, cómo funciona y preguntas frecuentes. No requiere una cuenta. El botón Iniciar sesión lleva al acceso existente; con sesión iniciada aparece Ir a mi portal. Los portales incluyen Ver sitio público y cerrar sesión devuelve a la página pública. El catálogo comparte los servicios de SQLite; no se exponen citas, pacientes ni otros datos privados. No se incorporó registro público.

Archivos: `clinical/templates/clinical/public.html` y `clinical/static/clinical/public.css`.
