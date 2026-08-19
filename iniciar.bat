@echo off
REM Abre el launcher grafico (la ventana de la app). Preferimos Gestos.vbs para
REM que no aparezca ninguna consola; este .bat es la alternativa por terminal.
REM
REM Busca un interprete que SIRVA de verdad: el entorno virtual de la carpeta si
REM esta sano, y si no el Python del sistema. Un .venv trae sus propios .exe,
REM pero son un REDIRECTOR al Python guardado en pyvenv.cfg: si la carpeta se
REM copia a otro equipo, a otro usuario o a otra unidad, esos .exe siguen ahi
REM apuntando a una ruta que ya no existe. Por eso no basta con que el archivo
REM exista, hay que comprobar que su Python base sigue en su sitio.

setlocal
cd /d "%~dp0"

set "PYW="
set "VENV_OK="

if exist ".venv\Scripts\pythonw.exe" call :comprobar_entorno
if defined VENV_OK set "PYW=.venv\Scripts\pythonw.exe"

if not defined PYW call :buscar pythonw.exe
if not defined PYW call :buscar pyw.exe

if defined PYW (
    REM pythonw = sin ventana de consola
    start "" "%PYW%" launcher.py
    goto :eof
)

echo.
echo No se encontro Python en este equipo.
echo.
echo   1) Instalalo desde https://www.python.org/downloads/
echo   2) Haz doble clic en preparar_entorno.bat, en esta misma carpeta
echo      (o a mano:  py -m venv .venv  y  .venv\Scripts\python.exe -m pip install -r requirements.txt)
echo.
pause
goto :eof


:comprobar_entorno
REM "home" es la carpeta del Python base del entorno virtual. Si ya no esta, el
REM entorno es de otro equipo y se ignora.
for /f "usebackq tokens=1,* delims== " %%A in (".venv\pyvenv.cfg") do (
    if /i "%%A"=="home" if exist "%%B\" set "VENV_OK=1"
)
if not defined VENV_OK echo [aviso] .venv apunta a un Python que no existe aqui; se ignora.
exit /b


:buscar
REM Primer %1 del PATH que sea un ejecutable de verdad. Los "alias de ejecucion"
REM de la Microsoft Store ocupan 0 bytes y solo abren la tienda.
for /f "delims=" %%P in ('where %1 2^>nul') do (
    if not defined PYW if %%~zP GTR 0 set "PYW=%%P"
)
exit /b
