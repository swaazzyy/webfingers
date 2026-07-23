@echo off
REM Lanzador del detector de gestos: doble clic y listo.
REM Usa el Python del entorno virtual de la carpeta, sin tocar el del sistema.

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo No se encuentra el entorno virtual .venv
    echo Crealo con:  py -3.13 -m venv .venv
    echo y luego:     .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

".venv\Scripts\python.exe" gestos_manos.py

REM Si algo falla, la ventana se queda abierta para poder leer el error.
if errorlevel 1 pause
