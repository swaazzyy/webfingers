@echo off
REM Deja la carpeta lista para funcionar en ESTE equipo: crea el entorno virtual
REM y instala las dependencias. Se puede ejecutar las veces que haga falta.
REM
REM Hace falta cuando descargas el codigo, y tambien cuando la carpeta viene
REM copiada de otro sitio: el .venv que traiga dentro es de aquel equipo (sus
REM .exe apuntan a un Python que aqui no existe) y hay que rehacerlo.

setlocal
cd /d "%~dp0"

echo.
echo === Preparando el entorno de Control por gestos ===
echo.

set "PY="
call :buscar py.exe
if not defined PY call :buscar python.exe
if not defined PY call :buscar python3.exe

if not defined PY (
    echo No se encontro Python en este equipo.
    echo.
    echo Instalalo desde https://www.python.org/downloads/ y vuelve a ejecutar
    echo este archivo. Marca la casilla "Add python.exe to PATH" al instalarlo.
    echo.
    pause
    exit /b 1
)
echo Python encontrado en: %PY%

set "EXTRA="
set "VENV_OK="
if exist ".venv\pyvenv.cfg" call :comprobar_entorno
if exist ".venv\pyvenv.cfg" if not defined VENV_OK set "EXTRA=--clear"
if defined EXTRA echo [aviso] El .venv que hay es de otro equipo: se rehace desde cero.

echo.
echo Creando el entorno virtual en .venv ...
"%PY%" -m venv .venv %EXTRA%
if errorlevel 1 goto :fallo

echo.
echo Instalando dependencias. La primera vez tarda varios minutos: mediapipe y
echo opencv juntos son casi 1 GB.
echo.
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fallo

echo.
echo === Listo ===
echo Abre Gestos.vbs (o iniciar.bat) para arrancar la aplicacion.
echo.
pause
goto :eof


:comprobar_entorno
REM "home" es la carpeta del Python base del entorno. Si ya no esta, el entorno
REM es de otro equipo y no sirve.
for /f "usebackq tokens=1,* delims== " %%A in (".venv\pyvenv.cfg") do (
    if /i "%%A"=="home" if exist "%%B\" set "VENV_OK=1"
)
exit /b


:buscar
REM Primer %1 del PATH que sea un ejecutable de verdad. Los "alias de ejecucion"
REM de la Microsoft Store ocupan 0 bytes y solo abren la tienda: no son Python.
for /f "delims=" %%P in ('where %1 2^>nul') do (
    if not defined PY if %%~zP GTR 0 set "PY=%%P"
)
exit /b


:fallo
echo.
echo No se pudo preparar el entorno. Revisa los mensajes de arriba.
echo.
pause
exit /b 1
