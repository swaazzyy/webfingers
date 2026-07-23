@echo off
REM Genera el ejecutable en dist\GestosManos\GestosManos.exe
cd /d "%~dp0"

if not exist ".venv\Scripts\pyinstaller.exe" (
    echo Falta PyInstaller en el entorno. Instalalo con:
    echo   .venv\Scripts\python.exe -m pip install pyinstaller pyinstaller-hooks-contrib
    pause
    exit /b 1
)

".venv\Scripts\pyinstaller.exe" --noconfirm --clean gestos_manos.spec
if errorlevel 1 ( echo. & echo FALLO la construccion. & pause & exit /b 1 )

REM Dejar el modelo junto al .exe para que funcione sin conexion desde el inicio
if exist "hand_landmarker.task" copy /y "hand_landmarker.task" "dist\GestosManos\" >nul

echo.
echo Listo: dist\GestosManos\GestosManos.exe
pause
