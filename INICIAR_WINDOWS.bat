@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto instalar
where python >nul 2>nul
if errorlevel 1 goto usar_py
python -m venv .venv
if errorlevel 1 goto error
goto instalar
:usar_py
py -m venv .venv
if errorlevel 1 goto error
:instalar
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto error
.venv\Scripts\python.exe manage.py migrate
if errorlevel 1 goto error
.venv\Scripts\python.exe manage.py preparar_demo
if errorlevel 1 goto error
echo.
echo Abre http://127.0.0.1:8000/ en tu navegador.
echo Para detener el servidor presiona Ctrl+C.
.venv\Scripts\python.exe manage.py runserver
pause
exit /b
:error
echo.
echo No se pudo iniciar GoClinical. Revisa el error mostrado arriba.
echo Consulta README.md para ejecutar los pasos manualmente.
pause
exit /b 1
