"""
Integracion con Windows: arranque automatico y accesos directos.

El arranque automatico se registra en HKCU\\...\\Run, que es la via para el
usuario actual y NO necesita permisos de administrador. Todo esta escrito para
que un fallo (registro protegido, sin permisos) se avise y no tumbe la app.
"""

from __future__ import annotations

import os
import subprocess
import sys
import winreg
from pathlib import Path

CLAVE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOMBRE_APP = "ControlPorGestos"


def carpeta_base() -> Path:
    """Carpeta del programa, funcione como script o empaquetado en .exe."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def comando_arranque() -> str:
    """Como lanzar la app, entrecomillado para rutas con espacios.

    Empaquetada es el propio .exe; como script, el pythonw del entorno (sin
    consola) o, si no existe, el python que este ejecutando.
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    base = carpeta_base()
    pyw = Path(sys.executable).with_name("pythonw.exe")
    interprete = pyw if pyw.exists() else Path(sys.executable)
    return f'"{interprete}" "{base / "launcher.py"}"'


# --------------------------------------------------------------------------- #
# Arranque automatico
# --------------------------------------------------------------------------- #

def autoarranque_activo() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLAVE_RUN) as k:
            winreg.QueryValueEx(k, NOMBRE_APP)
        return True
    except OSError:
        return False


def activar_autoarranque(comando: str | None = None) -> bool:
    """Registra la app para que se abra al iniciar sesion. True si lo consigue."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLAVE_RUN, 0,
                            winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, NOMBRE_APP, 0, winreg.REG_SZ,
                              comando or comando_arranque())
        return True
    except OSError as e:
        print(f"AVISO: no se pudo activar el arranque automatico: {e}")
        return False


def desactivar_autoarranque() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLAVE_RUN, 0,
                            winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, NOMBRE_APP)
        return True
    except FileNotFoundError:
        return True                      # no estaba: el resultado es el mismo
    except OSError as e:
        print(f"AVISO: no se pudo desactivar el arranque automatico: {e}")
        return False


def sincronizar_autoarranque(activo: bool) -> bool:
    """Deja el registro como diga `activo`. Devuelve el estado real resultante."""
    if activo:
        return activar_autoarranque() and autoarranque_activo()
    desactivar_autoarranque()
    return autoarranque_activo()


# --------------------------------------------------------------------------- #
# Accesos directos y carpetas
# --------------------------------------------------------------------------- #

def escritorio() -> Path:
    return Path(os.path.expanduser("~")) / "Desktop"


def menu_inicio() -> Path:
    return (Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" /
            "Start Menu" / "Programs")


def crear_acceso(destino: Path, objetivo: str, argumentos: str = "",
                 icono: str = "", carpeta_trabajo: str = "") -> bool:
    """Crea un .lnk con WScript.Shell, sin dependencias externas.

    Se usa un pequeno script VBS porque el objeto COM esta siempre disponible
    en Windows y evita tener que instalar pywin32.
    """
    vbs = f'''Set s = CreateObject("WScript.Shell")
Set a = s.CreateShortcut("{destino}")
a.TargetPath = "{objetivo}"
a.Arguments = "{argumentos}"
a.WorkingDirectory = "{carpeta_trabajo}"
{f'a.IconLocation = "{icono}"' if icono else ""}
a.Save
'''
    tmp = Path(os.environ.get("TEMP", ".")) / "_acceso_gestos.vbs"
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(vbs, encoding="utf-8")
        subprocess.run(["wscript", "//nologo", str(tmp)], check=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return destino.exists()
    except (OSError, subprocess.SubprocessError) as e:
        print(f"AVISO: no se pudo crear el acceso directo: {e}")
        return False
    finally:
        tmp.unlink(missing_ok=True)


def abrir(url_o_ruta: str) -> None:
    """Abre una URL en el navegador o una carpeta en el Explorador."""
    try:
        os.startfile(url_o_ruta)          # noqa: S606  (API de Windows)
    except OSError:
        subprocess.Popen(["cmd", "/c", "start", "", url_o_ruta], shell=False)
