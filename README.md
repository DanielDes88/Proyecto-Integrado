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

## Bases de datos y documentos

Django usa SQLite (`db.sqlite3`) por defecto para desarrollo local. Para usar PostgreSQL, configura `DATABASE_URL` con la URL de conexión de Neon antes de iniciar Django. La configuración requiere SSL y usa el driver Psycopg incluido en `requirements.txt`. `DATABASE_CONN_MAX_AGE` controla conexiones persistentes; queda en `0` por defecto para compatibilidad inicial con Neon Pooler. Ejecuta `manage.py migrate` para crear el esquema en la base indicada. Este comando **no copia datos desde SQLite**; `db.sqlite3` queda intacta y la migración de registros debe planificarse por separado.

### Configurar Neon paso a paso

1. En Neon, crea un proyecto PostgreSQL y copia la cadena de conexión. Mantén la contraseña privada. Para ejecutar migraciones puedes usar la conexión directa; para ejecutar la aplicación puedes usar la cadena pooled de Neon. Ambas deben incluir SSL.
2. Desde la carpeta del proyecto, activa el entorno e instala dependencias si aún no lo hiciste: `source .venv/bin/activate` y `pip install -r requirements.txt`.
3. En la misma terminal, exporta la cadena directa de Neon. No la guardes en Git ni la pegues en el chat:

	```bash
	export DATABASE_URL='postgresql://USUARIO:CLAVE@HOST_NEON/BASE?sslmode=require'
	```

	En PowerShell usa `$env:DATABASE_URL = 'postgresql://USUARIO:CLAVE@HOST_NEON/BASE?sslmode=require'`. Si la clave contiene caracteres especiales, usa la URL ya codificada que entrega Neon.
4. Comprueba qué motor cargó Django sin conectar ni modificar datos:

	```bash
	python manage.py shell -c "from django.conf import settings; print(settings.DATABASES['default']['ENGINE'])"
	```

	Debe mostrar `django.db.backends.postgresql`. Si muestra SQLite, no continúes: `DATABASE_URL` no llegó al proceso.
5. Revisa el plan y aplica el esquema en Neon:

	```bash
	python manage.py check
	python manage.py migrate --plan
	python manage.py migrate
	python manage.py showmigrations
	```

	Esto crea tablas de Django, sesiones, `clinical` y documentos. No cambia `db.sqlite3` ni importa sus registros.
6. Para crear solo las cuentas y datos ficticios de demostración en Neon, ejecuta `python manage.py preparar_demo`. No lo uses como mecanismo para trasladar datos reales.
7. Para iniciar la aplicación usando Neon, conserva `DATABASE_URL` en esa misma terminal y ejecuta `python manage.py runserver`. Para usar la conexión pooled en ejecución, reemplaza el valor por la cadena pooled de Neon. El valor `DATABASE_CONN_MAX_AGE=0` recomendado no mantiene conexiones persistentes.
8. Cuando cierres la terminal, esas variables desaparecen. Configúralas en el entorno del despliegue o expórtalas de nuevo para otra sesión. No es necesario ni recomendable escribir contraseñas en `settings.py`.

La primera vez que se use Neon, `showmigrations` mostrará migraciones pendientes allí aunque SQLite ya tenga varias aplicadas. Esto es normal: son bases independientes.

### Trasladar los registros actuales

Crear el esquema y copiar datos son tareas distintas. La aplicación no hace la copia automáticamente. Antes de trasladar registros desde `db.sqlite3`, respalda el archivo, define una ventana de mantenimiento y valida una exportación/importación en una base Neon vacía. No uses `preparar_demo` para copiar. Los metadatos de documentos se guardan en PostgreSQL, pero los bytes están en MongoDB y deben permanecer o trasladarse por un procedimiento separado; cambiar `DATABASE_URL` no mueve archivos entre servicios. No ejecutes una importación de datos reales hasta haber verificado relaciones, conteos y acceso a los documentos.

Los documentos se guardan en dos partes: PostgreSQL (o SQLite local) contiene el registro relacional, propietario, cita, categoría y referencia; MongoDB conserva el contenido como BSON `Binary` en la colección `clinical_documents`, sin GridFS. Configura `MONGODB_URI` y, opcionalmente, `MONGODB_DATABASE` (por defecto `goclinical`). La conexión usa TLS. El límite de carga es 10 MiB y solo se aceptan PDF, PNG y JPEG reconocidos por su firma.

Contrato backend para integrar la interfaz:

- `GET /api/documents/` lista metadatos visibles para el usuario autenticado.
- `POST /api/documents/upload/` recibe `multipart/form-data` con `file`, `category` y `appointment` (folio `GC-...`); requiere sesión y CSRF.
- `GET /api/documents/<id>/download/` transmite el contenido como archivo adjunto solo si el usuario conserva acceso.

Pacientes acceden a documentos propios y profesionales a documentos de citas asignadas. Administración no obtiene acceso general al contenido: solo ve o descarga archivos que subió. No hay transacción distribuida entre PostgreSQL y MongoDB; si falla el alta de metadatos, Django intenta borrar el BSON recién guardado. Esta función no incorpora análisis antimalware ni política de retención y no debe habilitarse con documentos clínicos reales antes de una revisión de seguridad, privacidad y requisitos legales.

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
