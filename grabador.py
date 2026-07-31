"""
Grabador de atajos: captura la combinacion de teclas que pulse el usuario.

Por que un hook de bajo nivel y no un `bind` de tkinter: Windows se queda para
si muchas combinaciones con la tecla Windows (Win+flecha, Win+D, Win+L...) y
nunca llegan a la aplicacion. Con un hook WH_KEYBOARD_LL las vemos ANTES que el
sistema, y ademas podemos tragarnoslas mientras se graba, para que grabar
"Win + flecha arriba" no maximice la ventana en la que estas grabando.

Uso:
    g = GrabadorAtajos(al_terminar=lambda teclas: ...)
    g.iniciar()      # empieza a escuchar
    ...              # el usuario pulsa la combinacion
    g.detener()      # se llama solo al capturar; tambien se puede forzar
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from control_windows import MODIFICADORES, VK

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0104, 0x0105

# Todas las variantes (izquierda/derecha/generica) de cada modificador
VK_MODIFICADOR = {
    0x10: "shift", 0xA0: "shift", 0xA1: "shift",
    0x11: "ctrl", 0xA2: "ctrl", 0xA3: "ctrl",
    0x12: "alt", 0xA4: "alt", 0xA5: "alt",
    0x5B: "win", 0x5C: "win",
}
VK_ESCAPE = 0x1B

# Codigo de tecla -> nombre que usa la app. Se construye del mapa de salida,
# asi que lo que se graba siempre se puede volver a enviar.
NOMBRE_POR_VK = {codigo: nombre for nombre, codigo in VK.items()
                 if nombre not in MODIFICADORES}


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_void_p)]


PROC_HOOK = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int,
                               wintypes.WPARAM, wintypes.LPARAM)

# Declarar las firmas es obligatorio en 64 bits: por defecto ctypes asume int de
# 32 bits y trunca los handles, con lo que SetWindowsHookExW fallaba con el
# error 126 ("modulo no encontrado") y parecia que el sistema lo prohibia.
_user32.SetWindowsHookExW.restype = wintypes.HHOOK
_user32.SetWindowsHookExW.argtypes = [ctypes.c_int, PROC_HOOK,
                                      wintypes.HINSTANCE, wintypes.DWORD]
_user32.UnhookWindowsHookEx.restype = wintypes.BOOL
_user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
_user32.CallNextHookEx.restype = ctypes.c_long
_user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int,
                                   wintypes.WPARAM, wintypes.LPARAM]


def describir(teclas: tuple[str, ...]) -> str:
    """Combinacion legible para mostrarla: ('win','arriba') -> 'Win + Arriba'."""
    bonito = {"win": "Win", "ctrl": "Ctrl", "alt": "Alt", "shift": "Shift",
              "arriba": "↑", "abajo": "↓", "izquierda": "←", "derecha": "→",
              "espacio": "Espacio", "supr": "Supr", "esc": "Esc"}
    return " + ".join(bonito.get(t, t.upper()) for t in teclas)


class GrabadorAtajos:
    """Escucha el teclado y devuelve la primera combinacion completa.

    Una combinacion se cierra cuando se pulsa una tecla que NO es modificador:
    los modificadores que esten en ese momento pulsados son el prefijo. Pulsar
    Esc a secas cancela.

    IMPORTANTE: el hook NO llama a nadie ni se desinstala a si mismo. Solo deja
    el resultado en un atributo, y quien lo use lo recoge con `recoger()`. El
    motivo es que el hook se ejecuta DENTRO del despacho de mensajes de Windows,
    y llamar ahi a tkinter (que no es reentrante) o desinstalar el propio hook
    puede tumbar el proceso con un fallo que Python ni siquiera puede capturar.
    """

    def __init__(self, al_terminar=None, al_cancelar=None) -> None:
        self.al_terminar = al_terminar     # compatibilidad: lo invoca recoger()
        self.al_cancelar = al_cancelar
        self._hook = None
        self._pulsados: set[str] = set()
        self.capturado: tuple[str, ...] | None = None
        self.cancelado = False
        # La referencia al callback debe sobrevivir: si la recoge el GC,
        # Windows llamaria a memoria liberada.
        self._callback = PROC_HOOK(self._procesar)

    # -- ciclo de vida ------------------------------------------------------ #

    def activo(self) -> bool:
        return self._hook is not None

    def iniciar(self) -> bool:
        if self._hook is not None:
            return True
        self._pulsados.clear()
        self.capturado = None
        self.cancelado = False
        ctypes.set_last_error(0)
        # hMod = None es lo correcto para un hook de bajo nivel dentro del
        # propio proceso; pasar un handle de modulo lo hace fallar.
        self._hook = _user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._callback, None, 0)
        if not self._hook:
            self._hook = None
            print(f"AVISO: no se pudo instalar el hook de teclado "
                  f"(error {ctypes.get_last_error()}); no se puede grabar.")
            return False
        return True

    def detener(self) -> None:
        if self._hook is not None:
            _user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
        self._pulsados.clear()

    def cancelar(self) -> None:
        self.detener()
        if self.al_cancelar:
            self.al_cancelar()

    def recoger(self) -> tuple[str, ...] | None:
        """Se llama desde el bucle de la GUI, FUERA del hook.

        Devuelve la combinacion capturada (y desinstala el hook) o None si aun
        no hay nada. Si el usuario cancelo, desinstala y avisa.
        """
        if self.cancelado:
            self.cancelado = False
            self.detener()
            if self.al_cancelar:
                self.al_cancelar()
            return None
        teclas = self.capturado
        if teclas is None:
            return None
        self.capturado = None
        self.detener()                      # seguro: ya no estamos en el hook
        if self.al_terminar:
            self.al_terminar(teclas)
        return teclas

    # -- hook --------------------------------------------------------------- #

    def _procesar(self, ncode: int, wparam: int, lparam: int) -> int:
        if ncode != 0:                       # no es un evento para nosotros
            return _user32.CallNextHookEx(None, ncode, wparam, lparam)

        info = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        vk = info.vkCode
        bajando = wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)
        mod = VK_MODIFICADOR.get(vk)

        if mod:
            if bajando:
                self._pulsados.add(mod)
            else:
                self._pulsados.discard(mod)
            return 1                         # tragarse la tecla mientras se graba

        if not bajando:
            return 1

        if vk == VK_ESCAPE and not self._pulsados:
            self.cancelado = True            # lo recoge `recoger()`
            return 1

        nombre = NOMBRE_POR_VK.get(vk)
        if nombre is None:                   # tecla que la app no sabe reenviar
            return 1

        if self.capturado is None:           # solo la primera combinacion
            # Orden estable: modificadores primero y siempre en el mismo orden,
            # para que "Ctrl+Shift+S" y "Shift+Ctrl+S" sean el mismo atajo.
            self.capturado = tuple(
                m for m in MODIFICADORES if m in self._pulsados) + (nombre,)
        return 1
