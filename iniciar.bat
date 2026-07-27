@echo off
REM Abre el launcher grafico (la ventana de la app). Preferimos Gestos.vbs para
REM que no aparezca ninguna consola; este .bat es la alternativa por terminal.
REM Usa el entorno virtual de la carpeta si existe y, si no, el Python del sistema.

cd /d "%~dp0"

REM pythonw = sin ventana de consola
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" launcher.py
    goto :eof
)

where pythonw >nul 2>&1 && ( start "" pythonw launcher.py & goto :eof )
where pyw     >nul 2>&1 && ( start "" pyw launcher.py & goto :eof )
where python  >nul 2>&1 && ( python launcher.py & goto :eof )

echo.
echo No se encontro Python en este equipo.
echo Instalalo desde https://www.python.org/downloads/ y luego crea el entorno:
echo     py -m venv .venv
echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
pause
