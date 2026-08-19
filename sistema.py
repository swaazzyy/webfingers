"""
Integracion con Windows: arranque automatico, accesos directos y rendimiento.

El arranque automatico se registra en HKCU\\...\\Run, que es la via para el
usuario actual y NO necesita permisos de administrador. Todo esta escrito para
que un fallo (registro protegido, sin permisos) se avise y no tumbe la app.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import winreg
from ctypes import wintypes
from pathlib import Path

CLAVE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOMBRE_APP = "ControlPorGestos"

# --------------------------------------------------------------------------- #
# Rendimiento en segundo plano
# --------------------------------------------------------------------------- #

# Windows 11 ESTRANGULA los procesos cuya ventana esta minimizada: los baja de
# frecuencia y los manda a los nucleos de eficiencia (es "EcoQoS", pensado para
# que el portatil dure mas). Para casi cualquier programa esta muy bien; para
# este no, porque el cursor lo mueve el proceso de deteccion y en cuanto lo
# minimizas empieza a ir a tirones aunque la mano se mueva igual.
#
# Se puede renunciar a ese ahorro proceso a proceso, que es lo que hace
# `mantener_ritmo`. Es la misma llamada que usan los reproductores y los
# capturadores de pantalla para seguir yendo finos de fondo.
_ProcessPowerThrottling = 4
_VERSION_THROTTLING = 1
_EXECUTION_SPEED = 0x1
_IGNORE_TIMER_RESOLUTION = 0x4
_ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000


class _Throttling(ctypes.Structure):
    _fields_ = [("Version", wintypes.ULONG),
                ("ControlMask", wintypes.ULONG),
                ("StateMask", wintypes.ULONG)]


def _kernel32():
    """kernel32 con los tipos declarados.

    Declarar el tipo de retorno de `GetCurrentProcess` no es opcional: devuelve
    un pseudo-handle (-1) y, sin decirlo, ctypes lo trunca a 32 bits y todas las
    llamadas fallan con ERROR_INVALID_HANDLE sin que se note por que.
    """
    k32 = ctypes.windll.kernel32
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.SetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                          ctypes.c_void_p, wintypes.DWORD]
    k32.SetProcessInformation.restype = wintypes.BOOL
    k32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k32.SetPriorityClass.restype = wintypes.BOOL
    return k32


def mantener_ritmo(prioridad: bool = False) -> dict:
    """Pide a Windows que no frene este proceso al pasar a segundo plano.

    Con `prioridad` ademas sube la clase de prioridad un escalon (no a "alta":
    eso puede dejar sin CPU al resto del sistema, y aqui solo hace falta llegar
    a tiempo, no ganarle a todo el mundo).

    Devuelve que ha funcionado de cada cosa. Nunca lanza: en una version de
    Windows que no conozca estas llamadas, la app tiene que seguir arrancando.
    """
    resultado = {"estrangulamiento": False, "reloj": False, "prioridad": False}
    try:
        k32 = _kernel32()
        info = _Throttling()
        info.Version = _VERSION_THROTTLING
        # ControlMask = "quiero decidir yo sobre esto"; StateMask = 0 = "no me
        # estrangules" y "no ignores mi resolucion de reloj de fondo".
        info.ControlMask = _EXECUTION_SPEED | _IGNORE_TIMER_RESOLUTION
        info.StateMask = 0
        resultado["estrangulamiento"] = bool(k32.SetProcessInformation(
            k32.GetCurrentProcess(), _ProcessPowerThrottling,
            ctypes.byref(info), ctypes.sizeof(info)))

        # Reloj fino: afecta a las esperas del bucle (waitKey, sleeps). Python
        # 3.11+ ya duerme con temporizador de alta resolucion, pero OpenCV no.
        resultado["reloj"] = ctypes.windll.winmm.timeBeginPeriod(1) == 0

        if prioridad:
            resultado["prioridad"] = bool(k32.SetPriorityClass(
                k32.GetCurrentProcess(), _ABOVE_NORMAL_PRIORITY_CLASS))
    except (OSError, AttributeError, ctypes.ArgumentError):
        pass                    # Windows antiguo: se sigue, solo que mas lento
    return resultado


def ventana_minimizada(titulo: str) -> bool:
    """True si la ventana con ese titulo existe y esta minimizada.

    Sirve para no gastar tiempo dibujando lo que nadie puede ver. OpenCV no lo
    cuenta (su `getWindowProperty` solo dice si sigue abierta), asi que se
    pregunta a Windows directamente.
    """
    try:
        u32 = ctypes.windll.user32
        u32.FindWindowW.restype = wintypes.HWND
        u32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        hwnd = u32.FindWindowW(None, titulo)
        return bool(hwnd) and bool(u32.IsIconic(hwnd))
    except (OSError, AttributeError):
        return False


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
