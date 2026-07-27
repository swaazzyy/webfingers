@echo off
REM Lanzador del detector de gestos: doble clic y listo.
REM Funciona en cualquier equipo: usa el entorno virtual de la carpeta si
REM existe y, si no, cualquier Python que haya instalado en el sistema.

cd /d "%~dp0"

REM 1) Entorno virtual junto al script (lo normal tras seguir el README)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" gestos_manos.py
    goto :fin
)

REM 2) Sin venv: probar el lanzador "py" y luego "python" del PATH
where py >nul 2>&1 && (
    echo No hay entorno virtual; usando el Python del sistema.
    py gestos_manos.py
    goto :fin
)
where python >nul 2>&1 && (
    echo No hay entorno virtual; usando el Python del sistema.
    python gestos_manos.py
    goto :fin
)

echo.
echo No se encontro Python en este equipo.
echo Instalalo desde https://www.python.org/downloads/ y luego crea el entorno:
echo     py -m venv .venv
echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
pause
exit /b 1

:fin
REM Si algo falla, la ventana se queda abierta para poder leer el error.
if errorlevel 1 pause
