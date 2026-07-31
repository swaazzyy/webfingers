@echo off
REM Genera los dos ejecutables:
REM   dist\ControlPorGestos\ControlPorGestos.exe  -> la aplicacion
REM   dist\InstalarControlPorGestos.exe           -> el instalador (un archivo)
cd /d "%~dp0"

if not exist ".venv\Scripts\pyinstaller.exe" (
    echo Falta PyInstaller en el entorno virtual. Instalalo con:
    echo   .venv\Scripts\python.exe -m pip install pyinstaller pyinstaller-hooks-contrib
    echo.
    echo Si aun no tienes el entorno, crealo primero:
    echo   py -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

".venv\Scripts\pyinstaller.exe" --noconfirm --clean gestos_manos.spec
if errorlevel 1 ( echo. & echo FALLO la construccion. & pause & exit /b 1 )

REM El modelo va junto al .exe para que funcione sin conexion desde el inicio
if exist "hand_landmarker.task" copy /y "hand_landmarker.task" "dist\ControlPorGestos\" >nul

echo.
echo Listo:
echo   Aplicacion : dist\ControlPorGestos\ControlPorGestos.exe
echo   Instalador : dist\InstalarControlPorGestos.exe
echo.
echo NOTA: los .exe no van firmados. Windows puede bloquearlos la primera vez
echo       (clic derecho ^> Propiedades ^> Desbloquear, o "Mas informacion" ^>
echo       "Ejecutar de todas formas" en SmartScreen).
pause
