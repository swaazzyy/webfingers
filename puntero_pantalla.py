"""
Puntero y estela dibujados encima del escritorio.

Es una ventana tkinter que cubre todo el escritorio virtual, sin bordes,
siempre visible y *click-through*: con los estilos WS_EX_TRANSPARENT |
WS_EX_NOACTIVATE el raton y los clics la atraviesan como si no existiera, no
roba el foco a ninguna aplicacion y el cursor del sistema se queda donde tu lo
dejaste. Todo lo que no se dibuja es 100 % transparente.

Solo depende de tkinter (biblioteca estandar) y ctypes.
"""

from __future__ import annotations

import ctypes
import tkinter as tk
from collections import deque

# Color clave: se vuelve 100 % transparente, asi solo se ve lo dibujado.
# Un magenta puro no coincide con ningun color del puntero.
CLAVE = "#ff00ff"

# Tono hacia el que se apaga la estela conforme envejece.
COLOR_APAGADO = (40, 40, 55)

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020      # los clics atraviesan la ventana
WS_EX_NOACTIVATE = 0x08000000       # nunca recibe el foco
WS_EX_TOOLWINDOW = 0x00000080       # no aparece en la barra de tareas ni Alt+Tab

_user32 = ctypes.WinDLL("user32", use_last_error=True)


def _a_rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _mezclar(color: str, destino: tuple[int, int, int], t: float) -> str:
    """Interpola `color` hacia `destino`; t=0 deja el color intacto."""
    r, g, b = _a_rgb(color)
    r = int(r + (destino[0] - r) * t)
    g = int(g + (destino[1] - g) * t)
    b = int(b + (destino[2] - b) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


class PunteroPantalla:
    """Punto de mira con estela, por encima de todas las ventanas."""

    def __init__(self, x0: int, y0: int, ancho: int, alto: int,
                 largo_estela: int = 26, grosor_max: int = 7) -> None:
        self.x0, self.y0 = x0, y0          # origen del escritorio virtual
        self.ancho, self.alto = ancho, alto
        self.grosor_max = grosor_max

        self._visible = False
        self._color = ""
        # Una posicion por frame; el limite marca cuanto dura la estela.
        self._estela: deque[tuple[int, int]] = deque(maxlen=largo_estela)

        self.raiz = tk.Tk()
        self.raiz.overrideredirect(True)          # sin barra de titulo ni bordes
        self.raiz.attributes("-topmost", True)
        self.raiz.attributes("-transparentcolor", CLAVE)
        # Formato "+-100": la forma documentada de dar offsets negativos, que
        # aparecen en cuanto hay un monitor a la izquierda o por encima.
        self.raiz.geometry(f"{ancho}x{alto}+{x0}+{y0}")
        self.raiz.configure(bg=CLAVE)

        self.lienzo = tk.Canvas(self.raiz, width=ancho, height=alto, bg=CLAVE,
                                highlightthickness=0, bd=0)
        self.lienzo.pack()

        # Los items se crean una sola vez y luego solo se mueven: crear y
        # destruir figuras en cada frame seria mucho mas caro.
        self._segmentos = [
            self.lienzo.create_line(0, 0, 0, 0, state="hidden", capstyle=tk.ROUND)
            for _ in range(largo_estela)
        ]
        self._anillo = self.lienzo.create_oval(0, 0, 0, 0, outline="", width=3)
        self._anillo_zoom = self.lienzo.create_oval(0, 0, 0, 0, outline="", width=2)
        self._centro = self.lienzo.create_oval(0, 0, 0, 0, fill="", outline="")
        self._cruz = [self.lienzo.create_line(0, 0, 0, 0, fill="", width=3)
                      for _ in range(4)]

        self.raiz.update_idletasks()
        self._hwnd = self.raiz.winfo_id()
        self._hacer_transparente_a_clics()
        self.raiz.withdraw()              # arranca oculto hasta el primer gesto
        self.raiz.update()

    # -- ventana ------------------------------------------------------------ #

    def _hacer_transparente_a_clics(self) -> None:
        estilo = _user32.GetWindowLongW(self._hwnd, GWL_EXSTYLE)
        _user32.SetWindowLongW(
            self._hwnd, GWL_EXSTYLE,
            estilo | WS_EX_LAYERED | WS_EX_TRANSPARENT
            | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
        )

    # -- dibujo ------------------------------------------------------------- #

    def _dibujar_estela(self, color: str) -> None:
        """Traza la ultima trayectoria del dedo, apagandose hacia el pasado."""
        puntos = self._estela
        n = len(puntos) - 1
        for i, item in enumerate(self._segmentos):
            if i >= n:
                self.lienzo.itemconfig(item, state="hidden")
                continue
            (x1, y1), (x2, y2) = puntos[i], puntos[i + 1]
            # t = 1 en la cola (mas antigua), 0 en la punta (el dedo)
            t = 1.0 - (i / n if n else 1.0)
            self.lienzo.coords(item, x1 - self.x0, y1 - self.y0,
                               x2 - self.x0, y2 - self.y0)
            self.lienzo.itemconfig(
                item, state="normal",
                width=max(1, int(self.grosor_max * (1.0 - t))),
                fill=_mezclar(color, COLOR_APAGADO, t))

    def _dibujar_puntero(self, x: int, y: int, color: str,
                         radio_zoom: float | None) -> None:
        cx, cy = x - self.x0, y - self.y0
        self.lienzo.coords(self._anillo, cx - 18, cy - 18, cx + 18, cy + 18)
        self.lienzo.coords(self._centro, cx - 4, cy - 4, cx + 4, cy + 4)
        self.lienzo.coords(self._cruz[0], cx - 28, cy, cx - 22, cy)
        self.lienzo.coords(self._cruz[1], cx + 22, cy, cx + 28, cy)
        self.lienzo.coords(self._cruz[2], cx, cy - 28, cx, cy - 22)
        self.lienzo.coords(self._cruz[3], cx, cy + 22, cx, cy + 28)

        if radio_zoom is None:
            self.lienzo.itemconfig(self._anillo_zoom, outline=CLAVE)
        else:
            r = max(6.0, min(radio_zoom, 240.0))
            self.lienzo.coords(self._anillo_zoom, cx - r, cy - r, cx + r, cy + r)
            self.lienzo.itemconfig(self._anillo_zoom, outline=color)

        if color != self._color:              # solo repintar si algo cambia
            self.lienzo.itemconfig(self._anillo, outline=color)
            self.lienzo.itemconfig(self._centro, fill=color)
            for linea in self._cruz:
                self.lienzo.itemconfig(linea, fill=color)
            self._color = color

    # -- API publica -------------------------------------------------------- #

    def mostrar(self, x: int, y: int, color: str = "#00e5ff",
                radio_zoom: float | None = None, estela: bool = True) -> None:
        """Coloca el puntero en (x, y) del escritorio y alarga la estela.

        `radio_zoom` (px) dibuja el anillo secundario: sirve para ver la
        apertura del calibre pulgar-indice mientras se hace zoom.
        """
        if not self._visible:
            self.raiz.deiconify()
            self._visible = True

        if estela:
            self._estela.append((int(x), int(y)))
            self._dibujar_estela(color)
        elif self._estela:
            self.limpiar_estela()

        self._dibujar_puntero(int(x), int(y), color, radio_zoom)
        self.raiz.update()                    # procesa el repintado, no bloquea

    def limpiar_estela(self) -> None:
        self._estela.clear()
        for item in self._segmentos:
            self.lienzo.itemconfig(item, state="hidden")

    def ocultar(self) -> None:
        if self._visible:
            self.limpiar_estela()
            self.raiz.withdraw()
            self._visible = False
            self.raiz.update()

    def cerrar(self) -> None:
        try:
            self.raiz.destroy()
        except tk.TclError:
            pass


class PunteroSimulado:
    """Sustituto sin ventana, para pruebas automaticas."""

    def __init__(self, *args, **kwargs) -> None:
        self.ultima_posicion: tuple[int, int] | None = None
        self.visible = False
        self.estela: list[tuple[int, int]] = []

    def mostrar(self, x, y, color="", radio_zoom=None, estela=True) -> None:
        self.ultima_posicion = (int(x), int(y))
        self.visible = True
        if estela:
            self.estela.append(self.ultima_posicion)

    def limpiar_estela(self) -> None:
        self.estela.clear()

    def ocultar(self) -> None:
        self.visible = False
        self.limpiar_estela()

    def cerrar(self) -> None:
        pass
