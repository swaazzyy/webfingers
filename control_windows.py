"""
Capa de Windows: metricas del escritorio, movimiento del cursor y zoom de la
ventana en primer plano.

- El cursor real se mueve con SendInput (movimiento absoluto sobre el escritorio
  virtual). No se envian clics: solo se desplaza la flecha del raton.
- El zoom se inyecta como Ctrl + '+' / Ctrl + '-', que van a la ventana que
  tengas seleccionada y son el atajo de zoom mas universal de Windows.

Se usa `SendInput` (user32) via ctypes, sin dependencias extra.

Modo simulacion: `EntradaWindows(simular=True)` imprime lo que haria en vez de
inyectar nada. Util para probar la logica sin tocar el sistema.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

# --------------------------------------------------------------------------- #
# Estructuras y constantes de la API SendInput
# --------------------------------------------------------------------------- #

ULONG_PTR = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

INPUT_RATON, INPUT_TECLADO = 0, 1
KEYEVENTF_KEYUP = 0x0002

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000          # coordenadas sobre todos los monitores

VK_CONTROL = 0x11
VK_OEM_PLUS, VK_OEM_MINUS = 0xBB, 0xBD    # teclas +/- de la fila principal
VK_ADD, VK_SUBTRACT = 0x6B, 0x6D          # teclado numerico (alternativa)

# Metricas del escritorio virtual (todos los monitores)
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class _UNION_INPUT(ctypes.Union):
    # MOUSEINPUT es el miembro mayor; con el, ctypes calcula el sizeof de INPUT
    # correcto en 32 y 64 bits (SendInput exige que cbSize coincida exacto).
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _UNION_INPUT)]


_user32 = ctypes.WinDLL("user32", use_last_error=True)


def habilitar_dpi() -> None:
    """Hace el proceso consciente del DPI para trabajar en pixeles fisicos.

    Sin esto, en pantallas con escalado (125 %, 150 %) las metricas que
    devuelve Windows estan escaladas y el puntero acaba desplazado.
    """
    try:                                     # Windows 10 1703+
        _user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except AttributeError:
        try:
            ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
        except OSError:
            _user32.SetProcessDPIAware()


# --------------------------------------------------------------------------- #
# Controlador
# --------------------------------------------------------------------------- #

class EntradaWindows:
    """Metricas de pantalla y envio del atajo de zoom a la ventana activa."""

    def __init__(self, simular: bool = False, teclado_numerico: bool = False) -> None:
        self.simular = simular
        # Algunas aplicaciones solo responden al +/- del teclado numerico.
        self.vk_mas = VK_ADD if teclado_numerico else VK_OEM_PLUS
        self.vk_menos = VK_SUBTRACT if teclado_numerico else VK_OEM_MINUS

        self._cursor_sim: tuple[int, int] | None = None   # cursor falso en simular
        if not simular:
            habilitar_dpi()
        # Origen y tamano del escritorio virtual (soporta varios monitores)
        self.x0 = _user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        self.y0 = _user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        self.ancho = max(1, _user32.GetSystemMetrics(SM_CXVIRTUALSCREEN))
        self.alto = max(1, _user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))

    # -- utilidades internas ------------------------------------------------ #

    def _enviar(self, *entradas: INPUT) -> int:
        """Inyecta los eventos en la cola de entrada del sistema."""
        if self.simular:
            return len(entradas)
        n = len(entradas)
        buffer = (INPUT * n)(*entradas)
        enviados = _user32.SendInput(n, buffer, ctypes.sizeof(INPUT))
        if enviados != n:
            raise ctypes.WinError(ctypes.get_last_error())
        return enviados

    @staticmethod
    def _tecla(vk: int, soltar: bool = False) -> INPUT:
        return INPUT(type=INPUT_TECLADO,
                     ki=KEYBDINPUT(wVk=vk, wScan=0,
                                   dwFlags=KEYEVENTF_KEYUP if soltar else 0,
                                   time=0, dwExtraInfo=0))

    # -- raton -------------------------------------------------------------- #

    def posicion_cursor(self) -> tuple[int, int]:
        """Posicion actual del cursor en pixeles del escritorio virtual."""
        if self.simular and self._cursor_sim is not None:
            return self._cursor_sim
        punto = wintypes.POINT()
        _user32.GetCursorPos(ctypes.byref(punto))
        return punto.x, punto.y

    def mover_cursor(self, x: int, y: int) -> None:
        """Coloca el cursor real en (x, y) del escritorio virtual.

        SendInput trabaja en un sistema normalizado 0..65535 sobre todo el
        escritorio; de ahi la conversion. Se recorta al area valida para no
        pedir coordenadas fuera de rango.
        """
        if self.simular:
            self._cursor_sim = (int(x), int(y))   # cursor coherente para pruebas
            return
        x = min(self.x0 + self.ancho - 1, max(self.x0, int(x)))
        y = min(self.y0 + self.alto - 1, max(self.y0, int(y)))
        nx = round((x - self.x0) * 65535 / max(1, self.ancho - 1))
        ny = round((y - self.y0) * 65535 / max(1, self.alto - 1))
        self._enviar(INPUT(type=INPUT_RATON, mi=MOUSEINPUT(
            dx=nx, dy=ny, mouseData=0, time=0, dwExtraInfo=0,
            dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE
            | MOUSEEVENTF_VIRTUALDESK)))

    # -- acciones publicas -------------------------------------------------- #

    def titulo_ventana_activa(self) -> str:
        """Titulo de la ventana en primer plano (solo para mostrarlo en el HUD)."""
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return ""
        n = _user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(n + 1)
        _user32.GetWindowTextW(hwnd, buffer, n + 1)
        return buffer.value

    def zoom(self, clics: int) -> None:
        """Ctrl + '+' / Ctrl + '-' sobre la ventana seleccionada.

        `clics` positivo = acercar, negativo = alejar.
        """
        if clics == 0:
            return
        if self.simular:
            print(f"[sim] zoom {clics:+d} clic(s)")
            return

        vk = self.vk_mas if clics > 0 else self.vk_menos
        # try/finally: pase lo que pase, Ctrl nunca se queda pulsado.
        self._enviar(self._tecla(VK_CONTROL))
        try:
            for _ in range(abs(clics)):
                self._enviar(self._tecla(vk), self._tecla(vk, soltar=True))
        finally:
            self._enviar(self._tecla(VK_CONTROL, soltar=True))

    def soltar_todo(self) -> None:
        """Red de seguridad al salir: asegura que Ctrl no queda pulsado."""
        if self.simular:
            print("[sim] soltar_todo")
            return
        try:
            self._enviar(self._tecla(VK_CONTROL, soltar=True))
        except OSError:
            pass
