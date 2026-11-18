# GoClinical Django — portales por usuario

Prototipo académico en Django y SQLite con inicio de sesión y vistas específicas para **paciente, profesional y administrador**, inspirado en los tres mockups de GoClinical adjuntos al proyecto. Los pagos se procesan con Flow en sandbox; los documentos son de demostración.

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
- Reservar, pagar en Flow sandbox y consultar el estado confirmado del pago.
- Cancelar visitas confirmadas.
- Evaluar una atención finalizada; el comentario queda pendiente de moderación.
- Ver perfil ficticio, historial de pagos y ayuda.

### Profesional

- Inicio con agenda programada y resumen de prestaciones.
- Ver únicamente las atenciones que tiene asignadas.
- Avanzar Confirmada → En camino → En atención → Finalizada.
- Crear o quitar bloques de disponibilidad, rechazando solapamientos.
- Consultar servicios y su perfil; cargar y descargar documentos vinculados a atenciones.
- Consultar honorarios ilustrativos (70 % del precio histórico) y registrar el envío de una boleta ficticia.

### Administrador

- Consultar resumen, tablas de solicitudes y gráficos calculados desde SQLite.
- Ver cuentas y pacientes del espacio de demostración.
- Aprobar o rechazar postulaciones ficticias.
- Consultar pagos y conteo de boletas ficticias recibidas.
- Aprobar comentarios; solo entonces pueden incluirse en la información disponible para el profesional.

## Recorrido de presentación

1. Ingresa como `paciente` y agenda una atención desde Servicios.
2. Continúa a Flow sandbox para completar una transacción de prueba; verifica el resultado en Mis solicitudes.
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

La propuesta es una adaptación funcional y simplificada; no reproduce todas las pantallas de los PDFs. No hay login con Google/Apple, mapas reales, chat, notificaciones externas, revisión de certificados, reprogramación, visitas recurrentes ni emisión tributaria. Las boletas indican expresamente que son ejemplos.

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

Los documentos se guardan en dos partes: PostgreSQL (o SQLite local) contiene el registro relacional, propietario, cita, categoría y referencia; MongoDB conserva el contenido como BSON `Binary` en la colección `clinical_documents`, sin GridFS. La conexión se comprueba mediante `ping` y crea un índice por fecha al abrir la colección. No necesitas configurar Neon para desarrollar con SQLite local; sí necesitas MongoDB para cargar y descargar archivos. La interfaz está en Mi perfil para pacientes y profesionales y usa Bootstrap 5.3 para el formulario y el listado responsivos. El límite de carga es 10 MiB y solo se aceptan PDF, PNG y JPEG reconocidos por su firma.

### Conectar MongoDB Atlas

Estos pasos deben completarse antes de cargar documentos:

1. En [MongoDB Atlas](https://www.mongodb.com/atlas), crea un proyecto y un clúster.
2. En **Security → Database Access**, crea un **Database User** para la aplicación. Esta contraseña es independiente de la contraseña de tu cuenta de Atlas. Asígnale permisos `readWrite` sobre la base `goclinical`.
3. En **Security → Network Access**, agrega la IP pública desde la que ejecutarás Django con **Add My Current IP Address**. Si cambia tu red, tendrás que actualizar esta regla. No uses `0.0.0.0/0` salvo para una prueba temporal.
4. En el clúster, selecciona **Connect → Drivers**, elige **Python** y copia la connection string. Debe comenzar con `mongodb+srv://`.
5. Reemplaza `USUARIO`, `CONTRASEÑA` y el host del clúster. Si la contraseña contiene caracteres especiales, codifícala para URL (`@` → `%40`, `#` → `%23`, `:` → `%3A`, `/` → `%2F`).
6. Desde PowerShell, en la raíz del proyecto, configura la connection string en la misma terminal donde ejecutarás Django:

```powershell
$env:MONGODB_URI = "mongodb+srv://USUARIO:CONTRASEÑA@CLUSTER/..."
$env:MONGODB_DATABASE = "goclinical"
$env:MONGODB_TLS = "1"
```

`MONGODB_TLS=1` es la configuración recomendada para Atlas. Estas variables duran mientras la terminal permanezca abierta; no guardes la connection string en Git, README, `.env` versionado ni la compartas por chat.

Comprueba que las variables estén presentes sin imprimir la contraseña:

```powershell
Write-Host "URI configurada: $([bool]$env:MONGODB_URI)"
Write-Host "Base configurada: $env:MONGODB_DATABASE"
Write-Host "TLS configurado: $env:MONGODB_TLS"
```

Instala las dependencias y verifica la aplicación y la conexión:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py check_mongodb
```

El resultado esperado de `check_mongodb` es:

```text
Conexión a MongoDB verificada.
```

Si aparece un error de autenticación, revisa el usuario y la contraseña de **Database Access**. Si aparece un timeout, revisa **Network Access**, que el clúster esté activo y que la red permita la conexión. Si `MONGODB_URI` no está configurada o MongoDB no responde, la aplicación permanece disponible, pero la carga y descarga de documentos responden con error de almacenamiento; no se aceptan documentos parcialmente guardados.

### Compartir la configuración de prueba con el equipo

La connection string de Atlas **no debe subirse al repositorio** ni compartirse en el chat o en archivos versionados. Cada integrante debe configurarla como variable de entorno en su propia terminal. El archivo `.env`, si se usa localmente, está excluido por `.gitignore`.

Para publicar los cambios en `dev`, revisa primero que no haya secretos ni archivos privados y ejecuta:

```powershell
git status
git diff --check
git add requirements.txt config/settings.py clinical/document_store.py clinical/management/commands/check_mongodb.py README.md
git commit -m "Integra almacenamiento de documentos con MongoDB"
git pull --rebase origin dev
git push origin dev
```

Si tienes cambios locales sin confirmar en `requirements.txt` u otro archivo, guárdalos con `git stash` antes de cambiar de rama o actualizar `dev`. Revisa siempre `git status` y `git diff` antes de confirmar.

En Atlas, crea un usuario de base de datos exclusivo para las pruebas con permisos `readWrite` sobre `goclinical`. No compartas la contraseña de tu cuenta de Atlas. En **Security → Network Access**, agrega la IP pública de cada integrante con **Add My Current IP Address**. La regla `0.0.0.0/0` solo debe usarse temporalmente y eliminarse después de la prueba.

Cada compañero debe preparar su copia local con:

```powershell
cd C:\ruta\Proyecto-Integrado
git switch dev
git pull --ff-only origin dev
py -3.15 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py preparar_demo
```

En la misma terminal, debe configurar su connection string privada y comprobar MongoDB:

```powershell
$env:MONGODB_URI = "mongodb+srv://USUARIO:CONTRASEÑA@CLUSTER.mongodb.net/?retryWrites=true&w=majority"
$env:MONGODB_DATABASE = "goclinical"
$env:MONGODB_TLS = "1"
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py check_mongodb
.\.venv\Scripts\python.exe manage.py runserver
```

Las variables `$env:MONGODB_*` duran mientras permanezca abierta esa terminal. Si se abre otra, deben configurarse nuevamente. Si la contraseña contiene caracteres especiales, debe estar codificada para URL; por ejemplo, `@` se escribe como `%40`.

MongoDB Atlas almacena los bytes de los documentos en `goclinical.clinical_documents`. Los usuarios, citas, permisos y metadata permanecen en la base relacional configurada por Django. Con SQLite local, cada integrante tendrá sus propios usuarios y citas de demostración aunque todos utilicen el mismo MongoDB; para compartir también esos datos se necesita una base relacional común, como PostgreSQL.

La interfaz usa estas APIs:

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

Los pagos usan Flow sandbox; no configures credenciales de producción en esta demostración. Aunque el prototipo permite cargar archivos, no se deben subir documentos clínicos reales: faltan análisis antimalware, políticas de retención y una revisión completa de seguridad, privacidad y requisitos legales. SQLite, DEBUG de desarrollo y las credenciales de ejemplo no son una configuración de producción.

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

## Pagos con Flow (sandbox)

El checkout usa la API REST oficial de Flow y queda configurado por defecto en `https://sandbox.flow.cl/api`. No cambies la URL a producción durante las pruebas. Configura las credenciales privadas de sandbox en la misma terminal desde la que ejecutarás Django:

```powershell
$env:FLOW_API_KEY = "tu-api-key-de-sandbox"
$env:FLOW_SECRET_KEY = "tu-secret-key-de-sandbox"
$env:FLOW_SITE_URL = "https://tu-dominio-publico"
```

`FLOW_SITE_URL` debe ser HTTPS y accesible públicamente para que Flow pueda llamar a `/api/payments/flow/confirmation/` y volver por `/payments/flow/return/`. En desarrollo local, usa un túnel HTTPS temporal. No publiques ni compartas `FLOW_SECRET_KEY`; no se almacena en la base de datos. `FLOW_API_URL` puede omitirse porque usa sandbox por defecto.

El servidor firma cada solicitud con HMAC-SHA256. La reserva queda pendiente hasta que el servidor consulta `payment/getStatus` a Flow y valida el token, el folio del comercio y el monto. El retorno del navegador no se considera prueba de pago. Si no se configuran credenciales o una URL HTTPS pública, el checkout devuelve un error explícito y no simula un pago. Consulta la [documentación oficial de Flow](https://www.flow.cl/docs/api.html).

### Requisitos y puesta en producción

La integración del repositorio queda en **sandbox**. No basta con cambiar la URL para considerarla lista para producción: antes de recibir pagos reales, completa y verifica todo lo siguiente:

1. **Habilita el comercio en Flow.** Completa la contratación/verificación de la cuenta y habilita los medios de pago que se ofrecerán. Solicita a Flow las credenciales de producción (`APIKey` y `SecretKey`) desde el canal seguro de tu cuenta. Las credenciales de sandbox y producción son distintas.
2. **Despliega GoClinical en un servidor público.** Usa un dominio propio con certificado TLS válido. Flow debe poder acceder por HTTPS, sin VPN ni autenticación HTTP, a `/api/payments/flow/confirmation/` y `/payments/flow/return/`. No sirven `localhost`, una IP privada ni un túnel temporal para producción.
3. **Configura secretos como variables del entorno de despliegue.** No los subas al repositorio, README, JavaScript, base de datos ni logs. En el entorno de producción establece:

   ```text
   FLOW_API_KEY=<APIKey de producción>
   FLOW_SECRET_KEY=<SecretKey de producción>
   FLOW_API_URL=https://www.flow.cl/api
   FLOW_SITE_URL=https://<dominio-publico>
   DJANGO_DEBUG=0
   DJANGO_SECRET_KEY=<secreto aleatorio nuevo y privado>
   DJANGO_ALLOWED_HOSTS=<dominio-publico>
   DATABASE_URL=<conexión PostgreSQL de producción con SSL>
   ```

   `FLOW_SITE_URL` es el origen HTTPS sin barra final. No reutilices la clave Django de desarrollo, las credenciales públicas de demostración ni credenciales compartidas por chat. Limita quién puede leer los secretos y planifica su rotación.
4. **Prepara la aplicación y la base de datos.** Usa PostgreSQL y un servidor WSGI/ASGI de producción; no expongas `runserver` ni SQLite como servicio de producción. Respalda la base y ejecuta `manage.py migrate` en el despliegue antes de servir tráfico. Configura archivos estáticos, HTTPS, hosts permitidos, cookies seguras y monitoreo de errores conforme al proveedor.
5. **Ejecuta la lista de pruebas de aceptación en sandbox antes de activar producción.** Verifica pago aprobado, rechazado, cancelado y pendiente; reintentos; callbacks duplicados; monto/folio no coincidentes; timeout y recuperación. Confirma los estados tanto en Flow como en GoClinical. Las pruebas automatizadas se ejecutan con `manage.py test clinical`; no reemplazan las pruebas de punta a punta con credenciales sandbox.
6. **Activa el endpoint productivo solo con aprobación.** Cambia `FLOW_API_URL` a `https://www.flow.cl/api` y carga exclusivamente credenciales productivas en el gestor de secretos del despliegue. Haz una compra real de bajo monto acordada con el comercio y verifica la liquidación en Flow. Vigila errores de callbacks y diferencias de conciliación después del lanzamiento.

El callback de confirmación está exento de CSRF porque lo llama Flow, pero no confía en el token recibido: consulta el estado en la API con la clave secreta y valida token, folio y monto antes de marcar `paid`. Mantén este flujo servidor-a-servidor y no aceptes confirmaciones desde el navegador. Esta versión no implementa reembolsos automáticos, conciliación contable, notificaciones al paciente ni reintentos de callback administrados; cancela una atención pagada no devuelve el dinero automáticamente. Define esos procesos operacionales y legales antes de vender servicios reales. Realiza además una revisión de seguridad, privacidad y cumplimiento aplicable al tratamiento de datos de salud en Chile; esta demostración académica no está certificada para datos clínicos reales.

Archivos: `clinical/templates/clinical/public.html` y `clinical/static/clinical/public.css`.
