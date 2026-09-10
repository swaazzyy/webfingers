"""
HUD de la ventana de deteccion, con el lenguaje visual de OBS Studio.

Hasta ahora la ventana de camara no escribia nada: para saber si el control
estaba activo, que gesto habia entendido o por que el cursor iba lento habia
que mirar el launcher, la chuleta del README o adivinarlo. Eso obliga a apartar
la vista justo cuando estas apuntando con la mano.

Se copia OBS Studio a proposito, porque resuelve exactamente el mismo problema:
enterarte del estado de un vistazo mientras miras otra cosa. De ahi salen todas
las piezas de aqui, una por una:

    - docks planos y oscuros con borde de 1 px y cabecera en mayusculas;
    - punto de "en directo" arriba a la izquierda (verde = control activo);
    - lista de fuentes con la fila activa resaltada -> aqui, las formas de la
      mano con la accion que tiene asignada cada una;
    - medidores del mezclador de audio, en bloques verde-amarillo-rojo y con la
      marca de pico que cae sola -> aqui, velocidad del puntero y calidad de la
      senal de deteccion;
    - barra de estado inferior con fps, CPU y frames perdidos.

Todo se dibuja con primitivas de OpenCV sobre el propio frame, sin ninguna
dependencia nueva. Los rellenos translucidos se mezclan SOLO en el recorte que
ocupa cada panel: un `addWeighted` sobre el frame entero costaba mas que la
propia deteccion.

Nota: la fuente de OpenCV (Hershey) no tiene acentos ni simbolos, asi que los
textos que vienen de `idiomas.py` (o los que escribe el usuario al grabar un
atajo) se transliteran antes de dibujarlos; ver `ascii_seguro`.
"""

from __future__ import annotations

import os
import time
from collections import deque

import cv2

import config

# --------------------------------------------------------------------------- #
# Paleta (BGR, que es como los quiere OpenCV)
# --------------------------------------------------------------------------- #

# Los grises del tema oscuro de OBS y sus dos acentos: el azul de la seleccion
# y el rojo de "grabando".
PANEL = (43, 43, 43)          # #2b2b2b, el fondo de los docks
CABECERA = (58, 58, 58)       # la tira del titulo del dock
BORDE = (66, 66, 66)
SELECCION = (70, 62, 52)      # fila activa: el azul de OBS muy rebajado
TEXTO = (222, 222, 222)
TENUE = (152, 152, 152)
APAGADO = (132, 132, 132)
ACENTO = (233, 174, 61)       # #3daee9
VIVO = (90, 200, 90)          # control activo
PAUSA = (110, 110, 110)
REC = (68, 68, 214)           # el rojo de OBS
SOMBRA = (16, 16, 16)

# Escala de los medidores, igual que en el mezclador: verde hasta que aprieta,
# amarillo cuando se acerca al limite y rojo cuando lo pasa.
VERDE = (72, 190, 72)
AMARILLO = (40, 200, 205)
ROJO = (48, 48, 210)

FUENTE = cv2.FONT_HERSHEY_SIMPLEX


# --------------------------------------------------------------------------- #
# Primitivas de dibujo
# --------------------------------------------------------------------------- #

# Lo que Hershey no sabe dibujar y tiene un equivalente razonable. El resto de
# caracteres raros (los emojis de las acciones, por ejemplo) simplemente se cae.
_EQUIVALENTES = {
    0xE1: "a", 0xE9: "e", 0xED: "i", 0xF3: "o", 0xFA: "u",
    0xC1: "A", 0xC9: "E", 0xCD: "I", 0xD3: "O", 0xDA: "U",
    0xF1: "n", 0xD1: "N", 0xFC: "u", 0xDC: "U",
    0x2022: "-", 0x00B7: "-", 0x2014: "-", 0x2013: "-", 0x00BA: "o",
    # Flechas: los atajos que graba el usuario se llaman con ellas ("Win + v"),
    # y sin esto el nombre llegaba al HUD partido por la mitad.
    0x2190: "<", 0x2191: "^", 0x2192: ">", 0x2193: "v",
}


def ascii_seguro(texto: str) -> str:
    """Deja un texto en lo que la fuente Hershey puede dibujar de verdad.

    Hershey no tiene acentos ni simbolos: lo que no conoce lo pinta como un
    cuadro vacio. Las etiquetas salen de `idiomas.py` (con tildes) y de los
    nombres que el usuario le pone a sus atajos (con lo que sea), asi que se
    transliteran al vuelo en vez de mantener una segunda tabla de textos solo
    para el HUD, que acabaria desincronizada.
    """
    limpio = texto.translate(_EQUIVALENTES)
    return " ".join("".join(c for c in limpio if 32 <= ord(c) < 127).split())


def ancho_texto(cadena: str, escala: float, grosor: int = 1) -> int:
    return cv2.getTextSize(ascii_seguro(cadena), FUENTE, escala, grosor)[0][0]


def texto(frame, cadena: str, x: int, y: int, escala: float,
          color=TEXTO, grosor: int = 1) -> int:
    """Escribe una linea (`y` es la BASE) y devuelve lo que ha ocupado.

    Siempre con una sombra de 1 px: el HUD flota sobre la imagen de la camara y
    sin ella el texto claro se pierde en cuanto pasa algo claro por detras.
    """
    cadena = ascii_seguro(cadena)
    if not cadena:
        return 0
    cv2.putText(frame, cadena, (x + 1, y + 1), FUENTE, escala, SOMBRA, grosor,
                cv2.LINE_AA)
    cv2.putText(frame, cadena, (x, y), FUENTE, escala, color, grosor,
                cv2.LINE_AA)
    return cv2.getTextSize(cadena, FUENTE, escala, grosor)[0][0]


def recortar_texto(cadena: str, ancho: int, escala: float) -> str:
    """Acorta con puntos suspensivos lo que no quepa en `ancho` pixeles."""
    cadena = ascii_seguro(cadena)
    if ancho_texto(cadena, escala) <= ancho:
        return cadena
    while cadena and ancho_texto(cadena + "...", escala) > ancho:
        cadena = cadena[:-1]
    return cadena.rstrip() + "..." if cadena else ""


def rect_translucido(frame, x: int, y: int, w: int, h: int, color,
                     alfa: float) -> None:
    """Rellena un rectangulo dejando ver la camara por debajo.

    Se mezcla solo el recorte que ocupa, no el frame entero: es la diferencia
    entre un HUD que no se nota en los fps y uno que se lleva media camara.
    """
    alto, ancho = frame.shape[:2]
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1, y1 = min(ancho, int(x + w)), min(alto, int(y + h))
    if x0 >= x1 or y0 >= y1:              # fuera del encuadre: nada que hacer
        return
    roi = frame[y0:y1, x0:x1]
    if alfa >= 1.0:
        roi[:] = color
        return
    capa = roi.copy()
    capa[:] = color
    # El resultado se asigna al recorte en vez de pedirle a OpenCV que escriba
    # dentro de el: `roi` es una vista del frame, y como destino directo OpenCV
    # se queja del formato en algunas versiones.
    roi[:] = cv2.addWeighted(capa, alfa, roi, 1.0 - alfa, 0.0)


def disco_translucido(frame, centro: tuple[int, int], radio: int, color,
                      alfa: float) -> None:
    """Como `rect_translucido` pero redondo; lo usa la mira del puntero."""
    x, y = centro
    alto, ancho = frame.shape[:2]
    x0, y0 = max(0, x - radio), max(0, y - radio)
    x1, y1 = min(ancho, x + radio + 1), min(alto, y + radio + 1)
    if x0 >= x1 or y0 >= y1:
        return
    roi = frame[y0:y1, x0:x1]
    capa = roi.copy()
    cv2.circle(capa, (x - x0, y - y0), radio, color, -1, cv2.LINE_AA)
    roi[:] = cv2.addWeighted(capa, alfa, roi, 1.0 - alfa, 0.0)


def color_nivel(fraccion: float) -> tuple[int, int, int]:
    """Color de la escala del mezclador segun la posicion en el medidor."""
    if fraccion >= 0.86:
        return ROJO
    if fraccion >= 0.62:
        return AMARILLO
    return VERDE


def apagar(color) -> tuple[int, int, int]:
    """Version oscurecida de un color, para los bloques que no estan encendidos.

    OBS pinta la escala entera siempre, apagada la parte que no llega, para que
    se vea de un vistazo cuanto margen queda; sin ella un medidor a media altura
    no dice nada.
    """
    return tuple(int(c * 0.34) for c in color)


def recortar(v: float, minimo: float, maximo: float) -> float:
    """Igual que la de `gestos_manos`, repetida aqui para no importarlo.

    `gestos_manos` importa este modulo; si este importase aquel, el ciclo
    romperia el arranque. Son tres lineas.
    """
    return max(minimo, min(maximo, v))


# --------------------------------------------------------------------------- #
# El HUD
# --------------------------------------------------------------------------- #

class HUD:
    """Capa de estado sobre la vista de camara.

    Es solo dibujo: no decide nada ni toca la deteccion. Todo lo que pinta se
    lo pasa el bucle principal ya calculado, para que el HUD no pueda acabar
    contando una cosa distinta de la que esta pasando.
    """

    ALTO_CABECERA = 18            # tira del titulo de cada dock, en px a e=1.0
    ALTO_TITULO = 26              # tira superior
    ALTO_ESTADO = 21              # tira inferior
    ALTO_MEDIDOR = 11
    ANCHO_GESTOS = 212
    ANCHO_PUNTERO = 232

    def __init__(self, t, mapa: dict | None = None,
                 cfg: dict | None = None) -> None:
        self.t = t                        # traductor de idiomas.py
        self.mapa = dict(mapa or {})      # forma de la mano -> accion
        self.cfg = cfg
        self.visible = True

        # --- Contadores del pie, al estilo de la barra de estado de OBS ----- #
        self._fps = 0.0
        self._ms = 0.0
        self._cpu = 0.0
        self._saltos = 0
        self._dts: deque[float] = deque(maxlen=60)
        self._t0 = time.perf_counter()
        self._cpu_marca = (time.perf_counter(), time.process_time())
        self._nucleos = max(1, os.cpu_count() or 1)

        # Pico del medidor de velocidad: sube al momento y baja despacio, como
        # la marca de pico del mezclador.
        self._pico = 0.0
        self._pico_t = time.perf_counter()
        # Ultimo atajo lanzado, para que su fila destelle un momento.
        self._destello = ""
        self._destello_t = 0.0

    # --- Textos ------------------------------------------------------------ #

    def _txt(self, clave: str) -> str:
        """Texto en el idioma activo."""
        return self.t(clave)

    def _accion(self, aid: str) -> str:
        """Nombre visible de una accion (el emoji se cae al pasar a ASCII)."""
        return config.etiqueta_accion(aid, self.t, self.cfg)

    # --- Medidas ----------------------------------------------------------- #

    def medir(self, dt: float, ms_proceso: float) -> None:
        """Contabiliza un frame. Llamar una vez por vuelta del bucle.

        `dt` son los segundos desde el frame anterior y `ms_proceso` lo que ha
        costado la inferencia mas el dibujo. Se separan a proposito: si los fps
        bajan pero el proceso sigue siendo rapido, el cuello de botella es la
        camara y no el equipo, que es justo lo que uno quiere saber cuando el
        puntero empieza a ir a tirones.
        """
        if dt > 0.0:
            # Media exponencial suave: un contador de fps que salta en cada
            # frame no se puede leer.
            self._fps += 0.12 * (1.0 / dt - self._fps)
        self._ms += 0.12 * (ms_proceso - self._ms)

        # "Frames perdidos": el hueco ha sido mas del doble de lo normal. No es
        # exacto (la camara no avisa de lo que tira), pero es la misma senal que
        # da OBS: el ritmo se ha roto y se nota en el puntero.
        if self._dts and dt > 2.2 * (sum(self._dts) / len(self._dts)):
            self._saltos += 1
        self._dts.append(dt)

        # CPU del proceso, repartida entre los nucleos del equipo (que es como
        # la cuenta OBS). `process_time` suma el tiempo de todos los hilos, asi
        # que sin dividir un equipo de 8 nucleos marcaria hasta 800%.
        ahora, cpu = time.perf_counter(), time.process_time()
        transcurrido = ahora - self._cpu_marca[0]
        if transcurrido >= 0.5:           # cada medio segundo: asi no parpadea
            self._cpu = 100.0 * (cpu - self._cpu_marca[1]) / (
                transcurrido * self._nucleos)
            self._cpu_marca = (ahora, cpu)

    def marcar_atajo(self, accion: str) -> None:
        """Avisa de que se acaba de lanzar un atajo, para destellar su fila."""
        self._destello = accion
        self._destello_t = time.perf_counter()

    # --- Piezas ------------------------------------------------------------ #

    def _dock(self, frame, x: int, y: int, w: int, h: int, titulo: str,
              e: float) -> int:
        """Panel con cabecera. Devuelve la Y donde empieza el contenido."""
        rect_translucido(frame, x, y, w, h, PANEL, 0.88)
        cab = int(round(self.ALTO_CABECERA * e))
        rect_translucido(frame, x, y, w, cab, CABECERA, 0.9)
        cv2.rectangle(frame, (x, y), (x + w - 1, y + h - 1), BORDE, 1)
        cv2.line(frame, (x, y + cab), (x + w - 1, y + cab), BORDE, 1)
        texto(frame, titulo, x + int(8 * e), y + int(round(cab * 0.72)),
              0.34 * e, TENUE)
        return y + cab

    def _medidor(self, frame, x: int, y: int, w: int, h: int, etiqueta: str,
                 valor: float, e: float, pico: float | None = None) -> None:
        """Medidor de bloques del mezclador de OBS.

        La escala entera se pinta siempre (apagada la parte a la que no llega),
        los bloques van de verde a rojo segun su posicion y, si se pasa un
        `pico`, se marca por donde iba el valor hace un momento.
        """
        col = int(40 * e)                 # columna de la etiqueta
        texto(frame, etiqueta, x, y + h - int(2 * e), 0.32 * e, TENUE)
        x += col
        w -= col
        if w <= int(8 * e):
            return

        rect_translucido(frame, x, y, w, h, (26, 26, 26), 0.85)
        bloques = max(8, int(w / max(2.0, 4.0 * e)))
        ancho_b = w / bloques
        encendidos = recortar(valor, 0.0, 1.0) * bloques
        for i in range(bloques):
            color = color_nivel((i + 0.5) / bloques)
            if i >= encendidos:           # aun no ha llegado: se deja apagado
                color = apagar(color)
            # -2 y no -1: `cv2.rectangle` incluye las dos esquinas, asi que con
            # -1 cada bloque acababa pegado al siguiente y el medidor salia como
            # una barra lisa, sin los segmentos que lo hacen legible de reojo.
            x0 = int(x + i * ancho_b)
            x1 = max(x0, int(x + (i + 1) * ancho_b) - 2)
            cv2.rectangle(frame, (x0, y + 1), (x1, y + h - 2), color, -1)
        if pico is not None and pico > 0.02:
            px = int(x + recortar(pico, 0.0, 1.0) * (w - 2))
            cv2.line(frame, (px, y + 1), (px, y + h - 2), TEXTO,
                     max(1, int(round(e))))
        cv2.rectangle(frame, (x, y), (x + w - 1, y + h - 1), BORDE, 1)

    def _barra_titulo(self, frame, ancho: int, e: float, control: bool,
                      accion: str, arrastrando: bool) -> None:
        """Tira superior: el punto de "en directo" y que se esta haciendo."""
        h = int(round(self.ALTO_TITULO * e))
        rect_translucido(frame, 0, 0, ancho, h, PANEL, 0.8)
        cv2.line(frame, (0, h), (ancho, h), BORDE, 1)

        # Punto de estado. Verde con el control activo, gris en pausa; el rojo
        # se reserva al boton pulsado, igual que el REC de OBS.
        if not control:
            color, estado = PAUSA, self._txt("hud_pausa")
        elif arrastrando:
            color, estado = REC, self._txt("hud_arrastre")
        else:
            color, estado = VIVO, self._txt("hud_activo")
        cy, cx = h // 2, int(14 * e)
        cv2.circle(frame, (cx, cy), int(round(5 * e)), color, -1, cv2.LINE_AA)
        cv2.circle(frame, (cx, cy), int(round(5 * e)), SOMBRA, 1, cv2.LINE_AA)
        texto(frame, estado, cx + int(12 * e), cy + int(4 * e), 0.42 * e,
              TEXTO if control else TENUE)

        # A la derecha, la accion que la mano esta ejecutando ahora mismo.
        etiqueta = recortar_texto(self._accion(accion), ancho // 2, 0.42 * e)
        if etiqueta:
            texto(frame, etiqueta,
                  ancho - ancho_texto(etiqueta, 0.42 * e) - int(14 * e),
                  cy + int(4 * e), 0.42 * e, ACENTO)

    def _alto_gestos(self, e: float) -> int:
        fila = int(round(19 * e))
        return (int(round(self.ALTO_CABECERA * e)) + fila * len(config.FORMAS)
                + int(6 * e))

    def _dock_gestos(self, frame, x: int, y: int, e: float, forma: str,
                     progreso: float) -> None:
        """Lista de formas de la mano, al estilo de las fuentes de una escena.

        Se ve de una vez que gestos existen y que hace cada uno, que era lo que
        obligaba a tener el README abierto al lado. La forma que la camara esta
        viendo va resaltada.
        """
        w = int(round(self.ANCHO_GESTOS * e))
        fila = int(round(19 * e))
        cy = self._dock(frame, x, y, w, self._alto_gestos(e),
                        self._txt("hud_gestos"), e) + int(3 * e)

        col = int(w * 0.44)               # columna forma | columna accion
        ahora = time.perf_counter()
        for fid in config.FORMAS:
            accion = self.mapa.get(fid, "nada")
            activa = fid == forma
            # Destello del atajo recien lanzado: dura poco a proposito, solo
            # para confirmar cual salio (el pitido no lo dice).
            reciente = (self._destello == accion
                        and ahora - self._destello_t < 0.4)
            if activa or reciente:
                rect_translucido(frame, x + 1, cy, w - 2, fila,
                                 SELECCION if activa else (36, 70, 36), 0.85)
                cv2.rectangle(frame, (x + 1, cy), (x + int(3 * e), cy + fila - 1),
                              VIVO if reciente else ACENTO, -1)

            base = cy + int(round(fila * 0.72))
            # "1 dedo - indice" -> "1 dedo": en una columna de 90 px no cabe la
            # explicacion, y el nombre corto ya identifica la forma.
            nombre = ascii_seguro(self._txt(f"forma_{fid}")).split("-")[0]
            texto(frame, recortar_texto(nombre, col - int(12 * e), 0.34 * e),
                  x + int(9 * e), base, 0.34 * e, TEXTO if activa else TENUE)
            texto(frame,
                  recortar_texto(self._accion(accion), w - col - int(10 * e),
                                 0.32 * e),
                  x + col, base, 0.32 * e, ACENTO if activa else APAGADO)

            # Barra del gesto mantenido (lanzar un atajo, activar el control):
            # sin ella no se sabe si falta un pelo o no se reconoce nada.
            if activa and progreso > 0.01:
                avance = int((w - 2) * recortar(progreso, 0.0, 1.0))
                cv2.rectangle(frame, (x + 1, cy + fila - max(1, int(2 * e))),
                              (x + 1 + avance, cy + fila - 1), ACENTO, -1)
            cy += fila

    def _alto_puntero(self, e: float) -> int:
        return (int(round(self.ALTO_CABECERA * e))
                + int(round(self.ALTO_MEDIDOR * e)) * 2 + int(36 * e))

    def _dock_puntero(self, frame, x: int, y: int, e: float, velocidad: float,
                      empuje: float, confianza: float, ganancia: float) -> None:
        """Medidores del puntero, con la forma del mezclador de audio."""
        w = int(round(self.ANCHO_PUNTERO * e))
        alto_m = int(round(self.ALTO_MEDIDOR * e))
        cy = self._dock(frame, x, y, w, self._alto_puntero(e),
                        self._txt("hud_puntero"), e) + int(7 * e)
        margen = int(9 * e)

        # Pico que baja solo, como el del mezclador: deja ver lo rapido que has
        # llegado a ir, que en movimiento no da tiempo a leer la barra.
        ahora = time.perf_counter()
        if velocidad >= self._pico:
            self._pico, self._pico_t = velocidad, ahora
        else:
            caida = 1.2 * (ahora - self._pico_t)   # escala entera en ~0,8 s
            self._pico = max(velocidad, self._pico - caida)
            self._pico_t = ahora

        self._medidor(frame, x + margen, cy, w - 2 * margen, alto_m,
                      self._txt("hud_vel"), velocidad, e, self._pico)
        cy += alto_m + int(5 * e)
        self._medidor(frame, x + margen, cy, w - 2 * margen, alto_m,
                      self._txt("hud_senal"), confianza, e)
        cy += alto_m + int(18 * e)

        # Lectura numerica: la velocidad configurada y cuanta ganancia se esta
        # aplicando de verdad en este instante (curva de precision/aceleracion).
        texto(frame, f"{self._txt('hud_ganancia')}  {ganancia:.1f}x",
              x + margen, cy, 0.34 * e, TENUE)
        der = f"{empuje:.1f}x"
        texto(frame, der, x + w - margen - ancho_texto(der, 0.34 * e), cy,
              0.34 * e, ACENTO)

    def _barra_estado(self, frame, ancho: int, alto: int, e: float) -> None:
        """Pie con reloj, fps, CPU y frames perdidos, como el de OBS."""
        h = int(round(self.ALTO_ESTADO * e))
        y = alto - h
        rect_translucido(frame, 0, y, ancho, h, PANEL, 0.8)
        cv2.line(frame, (0, y), (ancho, y), BORDE, 1)
        base = y + int(round(h * 0.68))
        esc = 0.34 * e

        seg = int(time.perf_counter() - self._t0)
        reloj = f"{seg // 3600:02d}:{seg % 3600 // 60:02d}:{seg % 60:02d}"
        # Sin punto de "grabando" delante del reloj: aqui no se graba nada, y
        # un circulo rojo en la barra decia justo lo contrario. El estado del
        # control ya lo lleva el punto de la tira de arriba, que es donde toca.
        x = int(10 * e)
        for cadena, color in (
                (reloj, TEXTO),
                (f"CPU: {self._cpu:.1f}%, {self._fps:.2f} fps", TENUE),
                (f"{ancho}x{alto}", TENUE),
                (f"{self._ms:.1f} ms", TENUE),
                (f"{self._txt('hud_perdidos')} {self._saltos}",
                 REC if self._saltos else TENUE)):
            x += texto(frame, cadena, x, base, esc, color) + int(16 * e)

        # Las teclas, a la derecha y solo si sobra sitio de verdad: es lo unico
        # prescindible de esta barra.
        pista = self._txt("hud_teclas")
        an = ancho_texto(pista, esc)
        if x + int(20 * e) + an < ancho:
            texto(frame, pista, ancho - an - int(10 * e), base, esc, APAGADO)

    # --- Dibujo ------------------------------------------------------------ #

    def dibujar(self, frame, *, control: bool, forma: str, accion: str,
                confianza: float = 0.0, velocidad: float = 0.0,
                empuje: float = 0.0, ganancia: float = 1.0,
                arrastrando: bool = False, progreso: float = 0.0) -> None:
        """Pinta el HUD entero sobre el frame (lo modifica, no devuelve nada).

        Los valores llegan ya calculados desde el bucle de deteccion; el HUD no
        los deduce por su cuenta para que no puedan contradecirse.
        """
        if not self.visible:
            return
        alto, ancho = frame.shape[:2]
        # Mismo criterio que la mira: 1.0 a 540 px de alto, acotado para que el
        # HUD no se coma un encuadre pequeno ni quede diminuto en 1080p.
        e = recortar(alto / 540.0, 0.75, 2.0)
        margen = int(10 * e)

        self._barra_titulo(frame, ancho, e, control, accion, arrastrando)
        self._dock_gestos(frame, margen, int(round(self.ALTO_TITULO * e)) + margen,
                          e, forma, progreso)
        self._dock_puntero(
            frame, ancho - int(round(self.ANCHO_PUNTERO * e)) - margen,
            alto - int(round(self.ALTO_ESTADO * e)) - margen
            - self._alto_puntero(e), e, velocidad, empuje, confianza, ganancia)
        self._barra_estado(frame, ancho, alto, e)
