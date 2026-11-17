# Verificación de portales por usuario

- Django 5.2.18, SQLite y Python 3.12 sobre Linux.
- Migraciones aplicadas correctamente, incluida la migración 0002 para perfiles y asignación de atenciones.
- `manage.py check`: sin incidencias.
- `manage.py makemigrations --check --dry-run`: sin cambios pendientes.
- `manage.py test clinical`: **16 pruebas aprobadas**.
- `node --check`: sintaxis JavaScript correcta.
- Comprobación de renderizado lógico de **21 vistas** (6 paciente, 7 profesional, 8 administración) con los datos JSON reales generados por Django. Ejecutada en un entorno DOM simulado; no equivale a una prueba visual del navegador.

Las pruebas incluyen login por rol, credenciales incorrectas, limitación de intentos, acceso anónimo, rutas de otro perfil, acciones prohibidas, acceso a registros ajenos, asignación profesional, persistencia y visibilidad compartida, precios del servidor, idempotencia, solapamientos, transiciones, evaluación y moderación, cancelación, disponibilidad, boletas ficticias, postulaciones, CSRF, logout y preservación de contraseñas al repetir la preparación.

Se inspeccionaron visualmente las páginas relevantes de los tres mockups antes de adaptar la interfaz. No se pudo ejecutar una revisión visual automatizada del sitio porque la descarga del navegador de pruebas falló. El script BAT no fue ejecutado en Windows. No se realizaron pruebas de carga ni una auditoría completa de seguridad.

Para la presentación conviene revisar en Chrome o Edge a 360, 768 y 1366 px, y recorrer las tres cuentas. Los datos del prototipo son ficticios y no se realizan cobros.

Actualización de página pública: 16 pruebas Django aprobadas. Se comprobó respuesta 200 anónima en `/`, catálogo público sin bootstrap privado, enlace al portal para usuarios autenticados, redirección al login para portales anónimos y API privada con respuesta 401.
