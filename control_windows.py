"""
Capa de Windows: metricas del escritorio, movimiento del cursor y zoom de la
ventana en primer plano.

- El cursor real se mueve con SendInput (movimiento absoluto sobre el escritorio
  virtual) y se pulsan sus botones.
- Los gestos disparan ATAJOS DE TECLADO de Windows (Win+Flecha, Alt+Tab...),
  con `enviar_atajo`. Cualquier combinacion se describe como una tupla de
  nombres de tecla, asi que anadir atajos nuevos no toca este modulo.

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
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010

# Codigos de tecla virtual. Los atajos se escriben con estos nombres, asi que
# anadir combinaciones nuevas no exige tocar codigo: basta con la tupla.
VK = {
    # modificadores
    "win": 0x5B, "ctrl": 0x11, "alt": 0x12, "shift": 0x10,
    # navegacion y edicion
    "tab": 0x09, "esc": 0x1B, "enter": 0x0D, "espacio": 0x20,
    "supr": 0x2E, "inicio": 0x24, "fin": 0x23,
    "arriba": 0x26, "abajo": 0x28, "izquierda": 0x25, "derecha": 0x27,
    "+": 0xBB, "-": 0xBD, ".": 0xBE, ",": 0xBC,
    # multimedia
    "vol_subir": 0xAF, "vol_bajar": 0xAE, "silencio": 0xAD,
    "play": 0xB3, "siguiente": 0xB0, "anterior": 0xB1,
    # funcion
    "f4": 0x73, "f5": 0x74, "f11": 0x7A, "imprpant": 0x2C,
}
# Letras y digitos: su VK coincide con el ASCII de la mayuscula
VK.update({c: ord(c.upper()) for c in "abcdefghijklmnopqrstuvwxyz0123456789"})

MODIFICADORES = ("win", "ctrl", "alt", "shift")

# Teclas EXTENDIDAS: hay que marcarlas con KEYEVENTF_EXTENDEDKEY o Windows las
# confunde con las del teclado numerico (VK_UP sin este bit se comporta como el
# 8 del numpad, y por eso Win+Flecha no maximizaba la ventana).
KEYEVENTF_EXTENDEDKEY = 0x0001
VK_EXTENDIDAS = {
    0x25, 0x26, 0x27, 0x28,          # flechas
    0x21, 0x22, 0x23, 0x24,          # RePag, AvPag, Fin, Inicio
    0x2D, 0x2E,                      # Insert, Supr
    0x5B, 0x5C,                      # Win izquierda y derecha
    0x90,                            # BloqNum
    0xA3, 0xA5,                      # Ctrl y Alt derechos
    0xAD, 0xAE, 0xAF,                # volumen
    0xB0, 0xB1, 0xB2, 0xB3,          # multimedia
}

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
    """Metricas de pantalla, cursor, botones y atajos de teclado de Windows."""

    def __init__(self, simular: bool = False) -> None:
        self.simular = simular
        self._cursor_sim: tuple[int, int] | None = None   # cursor falso en simular
        self.izq_pulsado = False          # estado de los botones, para poder
        self.der_pulsado = False          # soltarlos siempre al terminar
        self.entrada_bloqueada = False    # True si Windows rechaza SendInput
        self._aviso_bloqueo = False       # el aviso se imprime una sola vez
        if not simular:
            habilitar_dpi()
        # Origen y tamano del escritorio virtual (soporta varios monitores)
        self.x0 = _user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        self.y0 = _user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        self.ancho = max(1, _user32.GetSystemMetrics(SM_CXVIRTUALSCREEN))
        self.alto = max(1, _user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))

    # -- utilidades internas ------------------------------------------------ #

    def _enviar(self, *entradas: INPUT) -> int:
        """Inyecta los eventos en la cola de entrada del sistema.

        NO lanza excepcion si Windows rechaza la inyeccion: eso mataria el bucle
        de deteccion entero. Pasa de verdad —una politica de seguridad, un
        antivirus o una ventana elevada en primer plano pueden bloquear la
        entrada sintetica— y ante eso la app debe seguir viva y avisar una vez.
        Devuelve cuantos eventos se enviaron (0 = bloqueado).
        """
        if self.simular:
            return len(entradas)
        n = len(entradas)
        buffer = (INPUT * n)(*entradas)
        ctypes.set_last_error(0)
        enviados = _user32.SendInput(n, buffer, ctypes.sizeof(INPUT))
        if enviados != n:
            self.entrada_bloqueada = True
            if not self._aviso_bloqueo:
                self._aviso_bloqueo = True
                codigo = ctypes.get_last_error()
                print(f"AVISO: Windows rechazo la entrada sintetica "
                      f"(SendInput error {codigo}). El cursor no se movera.\n"
                      f"       Suele ser una ventana ejecutada como "
                      f"administrador en primer plano, o un antivirus. "
                      f"La deteccion sigue funcionando.")
        else:
            self.entrada_bloqueada = False
        return enviados

    @staticmethod
    def _tecla(vk: int, soltar: bool = False) -> INPUT:
        """Evento de teclado, marcando las teclas extendidas como tales."""
        flags = KEYEVENTF_KEYUP if soltar else 0
        if vk in VK_EXTENDIDAS:
            flags |= KEYEVENTF_EXTENDEDKEY
        return INPUT(type=INPUT_TECLADO,
                     ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags,
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

    def _evento_raton(self, flags: int) -> None:
        """Envia un evento de raton sin desplazamiento (solo botones)."""
        self._enviar(INPUT(type=INPUT_RATON, mi=MOUSEINPUT(
            dx=0, dy=0, mouseData=0, time=0, dwExtraInfo=0, dwFlags=flags)))

    def boton(self, derecho: bool, presionar: bool) -> None:
        """Pulsa o suelta un boton del raton, evitando eventos repetidos.

        Mantener el estado permite dos cosas: arrastrar (pulsar, mover, soltar)
        y garantizar en `soltar_todo` que ningun boton se queda hundido.
        """
        pulsado = self.der_pulsado if derecho else self.izq_pulsado
        if pulsado == presionar:          # ya esta en ese estado: nada que hacer
            return

        if derecho:
            flags = MOUSEEVENTF_RIGHTDOWN if presionar else MOUSEEVENTF_RIGHTUP
            self.der_pulsado = presionar
        else:
            flags = MOUSEEVENTF_LEFTDOWN if presionar else MOUSEEVENTF_LEFTUP
            self.izq_pulsado = presionar

        if self.simular:
            lado = "der" if derecho else "izq"
            print(f"[sim] boton {lado} {'abajo' if presionar else 'arriba'}")
            return
        self._evento_raton(flags)

    def clic(self, derecho: bool) -> None:
        """Clic completo (pulsar y soltar) en el sitio donde este el cursor."""
        self.boton(derecho, True)
        self.boton(derecho, False)

    # -- acciones publicas -------------------------------------------------- #

    def enviar_atajo(self, teclas: tuple[str, ...]) -> bool:
        """Envia una combinacion de teclas, p. ej. ("win", "arriba").

        Los modificadores se mantienen pulsados mientras se teclea el resto y se
        sueltan siempre en el `finally`: dejar Win o Alt hundidos dejaria el
        equipo inservible. Devuelve False si alguna tecla no esta en el mapa.
        """
        if not teclas:
            return False
        # Una CADENA tambien es iterable: si por error llega "arriba" en vez de
        # ("win", "arriba"), recorrerla teclearia a-r-r-i-b-a. Paso ya vivido:
        # se rechaza de forma explicita en vez de escribir el nombre del atajo.
        if isinstance(teclas, str):
            print(f"AVISO: atajo mal formado (cadena en vez de tupla): {teclas!r}")
            return False
        desconocidas = [t for t in teclas if t not in VK]
        if desconocidas:
            print(f"AVISO: atajo con teclas desconocidas: {desconocidas}")
            return False

        if self.simular:
            print(f"[sim] atajo {'+'.join(teclas)}")
            return True

        mods = [t for t in teclas if t in MODIFICADORES]
        resto = [t for t in teclas if t not in MODIFICADORES]

        for m in mods:
            self._enviar(self._tecla(VK[m]))
        try:
            for k in resto:
                self._enviar(self._tecla(VK[k]), self._tecla(VK[k], soltar=True))
        finally:
            for m in reversed(mods):      # se sueltan en orden inverso
                self._enviar(self._tecla(VK[m], soltar=True))
        return True

    def soltar_todo(self) -> None:
        """Red de seguridad: suelta botones del raton y TODOS los modificadores.

        Dejar un boton o un modificador hundido dejaria el equipo inservible
        (arrastre infinito, o cada tecla convertida en atajo), asi que esto se
        llama siempre al salir, pase lo que pase.
        """
        try:
            self.boton(derecho=False, presionar=False)
            self.boton(derecho=True, presionar=False)
        except OSError:
            pass
        if self.simular:
            print("[sim] soltar_todo")
            return
        for m in MODIFICADORES:
            try:
                self._enviar(self._tecla(VK[m], soltar=True))
            except OSError:
                pass
