"""
Detector de gestos de mano en tiempo real (MediaPipe Tasks + OpenCV).

Todo se maneja con las manos; las teclas son solo un respaldo. Se mueve el
cursor real de Windows y se hacen clics con el.

Los gestos se distinguen por el NUMERO de dedos estirados, que es mucho mas
facil de hacer y de detectar que medir distancias entre puntas:

    1 dedo  (indice)             -> mueve el CURSOR REAL de Windows, de forma
                                    relativa (como un trackpad)
    2 dedos (indice + medio)     -> CLIC IZQUIERDO; mantenlos y mueve la mano
                                    para ARRASTRAR
    pulgar arriba                -> CLIC DERECHO
    5 dedos (mano abierta)       -> MAXIMIZAR la ventana (Win + flecha arriba)
    0 dedos (puno)               -> MINIMIZAR la ventana (Win + flecha abajo)
    3 dedos                      -> CAMBIAR DE APLICACION (Alt + Tab)
    pulgar + menique ("llamame") -> mantenido 1,2 s: activa/desactiva el control

Ningun gesto usa el anular ni obliga a mover el menique por separado, que son
los dedos mas dificiles de controlar de forma aislada.

Cada forma puede lanzar CUALQUIER atajo de Windows (ver el catalogo en
config.py); los de arriba son solo los que vienen por defecto. El puntero
siempre se maneja con el dedo indice y eso no se toca.

En pantalla NO se escribe ninguna indicacion: solo se dibuja el esqueleto de la
mano y la diana del puntero. La chuleta de gestos esta en el README.

Uso:
    python gestos_manos.py

Salir: tecla q / ESC, o cerrar la ventana con la X.
Tecla c: activa/desactiva el control (respaldo del gesto).

La primera ejecucion descarga el modelo `hand_landmarker.task` (~7 MB) desde
el repositorio oficial de MediaPipe y lo deja junto a este script.

Nota: la fuente de OpenCV (Hershey) no dibuja acentos ni 'n' con virgulilla,
por eso las etiquetas en pantalla van sin tildes.
"""

from __future__ import annotations

import math
import sys
import time
import urllib.request
from collections import Counter, deque
from pathlib import Path


def carpeta_base() -> Path:
    """Carpeta donde guardar/buscar archivos junto al programa.

    Empaquetado con PyInstaller, `__file__` apunta a una carpeta temporal que
    se borra al cerrar; ahi el sitio estable es el que contiene el propio .exe.
    Como script normal, es la carpeta de este fichero.
    """
    if getattr(sys, "frozen", False):        # corriendo como .exe
        return Path(sys.executable).parent
    return Path(__file__).parent

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision

import camara
import config
from control_windows import EntradaWindows

# --------------------------------------------------------------------------- #
# Configuracion
# --------------------------------------------------------------------------- #

# Camara --------------------------------------------------------------------- #
# None = detecta las camaras conectadas y, si hay mas de una, abre un menu para
# elegir. Pon un numero para forzar una en concreto (se salta el menu).
INDICE_CAMARA = None
CAMARAS_A_PROBAR = 4         # cuantos indices (0..N-1) explorar al detectar
MENU_CAMARA_SIEMPRE = False  # True = mostrar el menu en cada arranque
COMPARTIR_CAMARA = True      # True = usar MSMF para poder compartir con otras apps

# Resolucion que se le PIDE a la camara; puede no concederla, asi que el codigo
# siempre trabaja con el tamano real del frame recibido.
ANCHO, ALTO = 960, 540
NOMBRE_VENTANA = "Detector de gestos - MediaPipe"
# Una sola mano: se controla con una y evita el bug de que el puntero salte a
# la otra mano que aparezca en el encuadre. MediaPipe no garantiza el orden de
# las manos entre frames, asi que con 2 el "principal" bailaba de una a otra.
MAX_MANOS = 1
CONF_DETECCION = 0.6
CONF_PRESENCIA = 0.5
CONF_SEGUIMIENTO = 0.6      # un poco mas alto: tracking mas estable, menos saltos

# La inferencia se hace sobre una copia reducida del frame; los landmarks son
# normalizados (0..1), asi que se dibujan igual sobre el frame a tamano completo.
# 1.0 = sin reduccion; 0.5-0.7 acelera bastante con poca perdida de precision.
ESCALA_DETECCION = 0.6

VENTANA_SUAVIZADO = 5      # nº de frames para el voto mayoritario del gesto

# --- Control por gestos ---------------------------------------------------- #
CONTROL_ACTIVO = True      # estado inicial del control
SIMULAR_ENTRADA = False    # True = solo imprime las acciones, no toca el sistema

# Gesto mantenido para activar/desactivar el control (pulgar + menique):
ESPERA_CONTROL = 1.2       # segundos

# --- Puntero relativo (tipo raton / trackpad) ------------------------------ #
# El puntero se desplaza segun cuanto muevas la mano, no segun donde este; al
# bajar la mano y volver a apuntar continua desde donde se quedo (como levantar
# un raton para recolocarlo).
#
# CALIBRACION PORTABLE: todos estos valores son RELATIVOS, no pixeles. El
# desplazamiento del dedo se mide como fraccion del encuadre y se convierte a
# fraccion de la pantalla, asi que el tacto es el mismo en cualquier equipo,
# con cualquier resolucion de webcam y de monitor. Con pixeles crudos, la misma
# app iba disparada en una pantalla 1080p y lentisima en una 4K.
GANANCIA_PUNTERO = 2.0     # sensibilidad general (la ajusta el slider de la GUI)
ACELERACION = 1.4          # empuje extra en gestos rapidos (0 = velocidad constante)
VEL_ACEL_MAX = 0.05        # fraccion del encuadre por frame donde la acel. topa

# PRECISION: a baja velocidad el cursor avanza solo esta fraccion de la ganancia,
# para poder apuntar fino; a alta velocidad se suma la aceleracion para llegar
# lejos. Asi hay precision Y alcance sin elegir uno u otro.
PRECISION_PUNTERO = 0.45

# --- Filtro One-Euro para la punta del dedo -------------------------------- #
# Es el filtro estandar para punteros interactivos porque resuelve el dilema
# temblor-vs-retraso: adapta su corte a la velocidad. Quieto -> corte bajo, se
# come el ruido del landmark; en movimiento -> corte alto, sigue al dedo sin
# arrastre. Trabaja con TIEMPO REAL (dt), asi que el tacto no cambia si bajan
# los FPS. Un EMA fijo no puede hacer las dos cosas: o tiembla o se retrasa.
# Valores elegidos por barrido empirico (no a ojo): se probaron 50 combinaciones
# con ruido realista a 30 fps y se valido el ganador con 5 semillas distintas.
# Frente al EMA fijo anterior: 63x menos vibracion, 6x menos retraso al parar.
EURO_MINCUTOFF = 0.3       # Hz en reposo: mas bajo = menos temblor, mas retraso
EURO_BETA = 10.0           # cuanto sube el corte con la velocidad (menos lag)
EURO_DCUTOFF = 0.7         # Hz para suavizar la estimacion de velocidad

# Salto imposible en un frame (fraccion del encuadre): si la punta "teletransporta"
# mas que esto, es un glitch o que MediaPipe cambio de mano -> se reancla sin
# mover el cursor, en vez de pegar un latigazo.
SALTO_MAX = 0.35

ZONA_MUERTA = 0.0008       # fraccion del encuadre por debajo de la cual no se mueve

# --- Clics ------------------------------------------------------------------ #
# Los clics se distinguen por el NUMERO de dedos estirados, no por distancias
# finas entre puntas: es mucho mas facil de hacer y de detectar.
#   2 dedos (indice + medio)          -> clic izquierdo / arrastrar
#   3 dedos (indice + medio + anular) -> clic derecho
ESTABILIDAD_CLIC_DER = 0.15  # s que hay que mantener el pulgar arriba
UMBRAL_ARRASTRE = 0.02     # fraccion del encuadre a recorrer para pasar a arrastre

LARGO_ESTELA = 26          # posiciones que deja el rastro del dedo (0 = sin estela)
GROSOR_ESTELA = 7          # grosor del trazo en la punta

# --- Atajos de Windows ------------------------------------------------------ #
# Cada forma de la mano puede lanzar un atajo (maximizar, Alt+Tab, subir
# volumen...). Se dispara UNA VEZ y hay que soltar el gesto para repetirlo.
ESPERA_ATAJO = 0.35        # s que hay que mantener el gesto antes de lanzarlo

# Modelo: variante float16 (rapida). Para mas precision usar la ruta ".../full/..."
MODELO = carpeta_base() / "hand_landmarker.task"
URL_MODELO = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)

# Umbrales de la heuristica (normalizados por el tamano de la mano)
ANG_DEDO_EXTENDIDO = 155.0  # grados en la articulacion PIP
ANG_PULGAR_RECTO = 150.0    # grados en la articulacion IP del pulgar
ALTURA_MIN_PULGAR = 0.35    # cuanto debe subir el pulgar sobre la muneca

# --------------------------------------------------------------------------- #
# Etiquetas de gesto y colores
# --------------------------------------------------------------------------- #

# --- Formas de la mano (lo que detecta la camara) --------------------------- #
# Su id coincide con el del editor de gestos (ver config.py). Que accion hace
# cada una la decide el usuario en la GUI; aqui solo se reconocen.
UN_DEDO = "un_dedo"
DOS_DEDOS = "dos_dedos"
TRES_DEDOS = "tres_dedos"
PULGAR = "pulgar"
MANO_ABIERTA = "mano_abierta"
PUNO = "puno"
PULGAR_MENIQUE = "pulgar_menique"
DESCONOCIDO = "---"

# Patron de dedos (pulgar, indice, medio, anular, menique) -> forma. El pulgar
# es indiferente en las formas de dedos, asi que cada una aparece con el pulgar
# recogido y estirado.
PATRONES = {
    (0, 1, 0, 0, 0): UN_DEDO,
    (1, 1, 0, 0, 0): UN_DEDO,        # tambien la forma de "L"
    (0, 1, 1, 0, 0): DOS_DEDOS,
    (1, 1, 1, 0, 0): DOS_DEDOS,
    (0, 1, 1, 1, 0): TRES_DEDOS,
    (1, 1, 1, 1, 0): TRES_DEDOS,
    (1, 1, 1, 1, 1): MANO_ABIERTA,
    (0, 0, 0, 0, 0): PUNO,
    (1, 0, 0, 0, 1): PULGAR_MENIQUE,
}

# --- Acciones (lo que hace la app). Sus ids coinciden con config.py --------- #
MOVER = "mover"
CLIC_IZQ = "clic_izq"
CLIC_DER = "clic_der"
ALTERNAR = "alternar"
NADA = "nada"

ACCIONES_PUNTERO = (MOVER, CLIC_IZQ)     # acciones que gobiernan el cursor
# Todo lo que no sea de raton/control es un atajo de Windows
ACCIONES_APP = (MOVER, CLIC_IZQ, CLIC_DER, ALTERNAR, NADA)

# Color del esqueleto segun la accion que la mano esta ejecutando (BGR).
COLOR_ACCION = {
    MOVER: (220, 90, 220),
    CLIC_IZQ: (255, 255, 90),
    CLIC_DER: (120, 160, 255),
    ALTERNAR: (235, 180, 40),
    NADA: (170, 170, 170),
    DESCONOCIDO: (170, 170, 170),
}
COLOR_ATAJO = (60, 200, 60)              # verde para cualquier atajo de Windows

# --------------------------------------------------------------------------- #
# Indices de landmarks (mapa de 21 puntos de MediaPipe Hands)
# --------------------------------------------------------------------------- #

MUNECA = 0
PULGAR_MCP, PULGAR_IP, PULGAR_TIP = 2, 3, 4
INDICE_MCP, INDICE_TIP = 5, 8
MEDIO_MCP, MEDIO_TIP = 9, 12
MENIQUE_MCP = 17

# (mcp, pip, tip) de indice, medio, anular y menique
DEDOS_LARGOS = ((5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20))

# Aristas del esqueleto, precalculadas una sola vez
CONEXIONES = tuple(
    (c.start, c.end) for c in vision.HandLandmarksConnections.HAND_CONNECTIONS
)


# --------------------------------------------------------------------------- #
# Utilidades geometricas
# --------------------------------------------------------------------------- #

def distancia(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distancia euclidea entre dos puntos 2D."""
    return math.hypot(a[0] - b[0], a[1] - b[1])


def angulo(a: tuple[float, float], b: tuple[float, float],
           c: tuple[float, float]) -> float:
    """Angulo (en grados) del vertice `b` en el triangulo a-b-c."""
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    n1 = math.hypot(*v1)
    n2 = math.hypot(*v2)
    if n1 == 0.0 or n2 == 0.0:
        return 180.0
    cos = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def recortar(v: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, v))


# --------------------------------------------------------------------------- #
# Analisis de la mano
# --------------------------------------------------------------------------- #

def a_pixeles(landmarks, ancho: int, alto: int) -> list[tuple[float, float]]:
    """Convierte los landmarks normalizados a coordenadas de pixel.

    Se trabaja en pixeles (y no en 0..1) para que la relacion de aspecto no
    deforme los angulos ni las distancias de la heuristica.
    """
    return [(lm.x * ancho, lm.y * alto) for lm in landmarks]


def escala_mano(pts: list[tuple[float, float]]) -> float:
    """Tamano de referencia: muneca -> nudillo del dedo medio.

    Sirve para normalizar umbrales y que no dependan de la distancia a la camara.
    """
    return distancia(pts[MUNECA], pts[MEDIO_MCP]) or 1.0


def dedos_extendidos(pts: list[tuple[float, float]]) -> tuple[bool, ...]:
    """Devuelve (pulgar, indice, medio, anular, menique) como booleanos.

    La deteccion es angular, por lo que funciona con la mano en cualquier
    orientacion (no depende de que los dedos apunten hacia arriba).
    """
    munieca = pts[MUNECA]

    # Pulgar: la falange debe estar recta y la punta alejarse de la base del
    # menique (si el pulgar esta plegado sobre la palma, la punta queda mas
    # cerca de ese punto que la articulacion IP).
    pulgar_recto = angulo(pts[PULGAR_MCP], pts[PULGAR_IP],
                          pts[PULGAR_TIP]) > ANG_PULGAR_RECTO
    pulgar_fuera = (distancia(pts[PULGAR_TIP], pts[MENIQUE_MCP])
                    > distancia(pts[PULGAR_IP], pts[MENIQUE_MCP]))
    estados = [pulgar_recto and pulgar_fuera]

    # Dedos largos: articulacion PIP casi recta y punta mas lejos de la
    # muneca que la propia PIP.
    for mcp, pip, tip in DEDOS_LARGOS:
        recto = angulo(pts[mcp], pts[pip], pts[tip]) > ANG_DEDO_EXTENDIDO
        alargado = distancia(pts[tip], munieca) > distancia(pts[pip], munieca)
        estados.append(recto and alargado)

    return tuple(estados)


def clasificar_gesto(dedos: tuple[bool, ...],
                     pts: list[tuple[float, float]]) -> str:
    """Traduce el patron de dedos estirados a una FORMA de la mano.

    Es una simple consulta a `PATRONES`: cada forma es un numero de dedos
    distinto, sin umbrales de distancia entre puntas. El unico caso especial es
    el pulgar solo, que ademas tiene que apuntar hacia arriba de verdad.
    """
    patron = tuple(int(d) for d in dedos)

    if patron == (1, 0, 0, 0, 0):
        # Pulgar solo cuenta si apunta hacia arriba de verdad: un puno con el
        # pulgar asomando de lado no debe contar. En imagen la Y crece hacia
        # abajo, de ahi la comparacion invertida.
        arriba = (pts[PULGAR_TIP][1]
                  < pts[MUNECA][1] - ALTURA_MIN_PULGAR * escala_mano(pts))
        return PULGAR if arriba else DESCONOCIDO

    return PATRONES.get(patron, DESCONOCIDO)


class SuavizadorGesto:
    """Voto mayoritario sobre los ultimos N frames para evitar parpadeos."""

    def __init__(self, ventana: int = VENTANA_SUAVIZADO) -> None:
        self._historial: deque[str] = deque(maxlen=ventana)

    def actualizar(self, gesto: str) -> str:
        self._historial.append(gesto)
        return Counter(self._historial).most_common(1)[0][0]


class AccionSostenida:
    """Dispara una accion cuando un gesto se mantiene N segundos.

    Despues de disparar hay que soltar el gesto para volver a activarlo, asi
    que un puno prolongado no encadena encendidos y apagados.
    """

    def __init__(self, gesto: str, duracion: float) -> None:
        self.gesto = gesto
        self.duracion = duracion
        self._t0: float | None = None
        self._disparado = False

    def actualizar(self, gesto_actual: str) -> tuple[bool, float]:
        """Devuelve (se_dispara_ahora, progreso 0..1)."""
        if gesto_actual != self.gesto:
            self._t0 = None
            self._disparado = False
            return False, 0.0

        ahora = time.perf_counter()
        if self._t0 is None:
            self._t0 = ahora
        progreso = recortar((ahora - self._t0) / self.duracion, 0.0, 1.0)

        if progreso >= 1.0 and not self._disparado:
            self._disparado = True
            return True, 1.0
        return False, 0.0 if self._disparado else progreso


# --------------------------------------------------------------------------- #
# Puntero y zoom
# --------------------------------------------------------------------------- #

class UnEuro:
    """Filtro One-Euro de un eje (Casiez et al.).

    La idea: el corte del filtro paso-bajo no es fijo, sino que sube con la
    velocidad estimada de la senal. Parado filtra fuerte (mata el temblor del
    landmark) y en movimiento apenas filtra (no anade retraso).
    """

    def __init__(self, mincutoff: float, beta: float, dcutoff: float) -> None:
        self.mincutoff, self.beta, self.dcutoff = mincutoff, beta, dcutoff
        self._x: float | None = None       # ultimo valor filtrado
        self._dx = 0.0                     # velocidad filtrada (unidades/s)

    @staticmethod
    def _alfa(dt: float, corte: float) -> float:
        """Coeficiente EMA equivalente a un paso-bajo de `corte` Hz en `dt` s."""
        tau = 1.0 / (2.0 * math.pi * corte)
        return 1.0 / (1.0 + tau / dt)

    def reiniciar(self) -> None:
        self._x = None
        self._dx = 0.0

    def filtrar(self, valor: float, dt: float) -> float:
        if self._x is None:                # primer valor: nada que filtrar
            self._x = valor
            return valor

        # Velocidad, suavizada aparte para que su propio ruido no dispare el corte
        derivada = (valor - self._x) / dt
        self._dx += self._alfa(dt, self.dcutoff) * (derivada - self._dx)

        # Corte adaptativo: cuanto mas rapido va el dedo, menos se filtra
        corte = self.mincutoff + self.beta * abs(self._dx)
        self._x += self._alfa(dt, corte) * (valor - self._x)
        return self._x


class ControlPuntero:
    """Air-mouse relativo: la mano empuja el cursor real como el dedo un trackpad.

    No mapea la posicion del dedo a la pantalla, sino su *desplazamiento* entre
    frames, y con el mueve el cursor de Windows. Al perder el gesto se re-ancla
    a la posicion real del cursor, asi que puedes bajar la mano, volver a apuntar
    y el cursor sigue donde estaba (como levantar un raton para recolocarlo).
    """

    def __init__(self, entrada: EntradaWindows) -> None:
        self.entrada = entrada
        self._x, self._y = entrada.posicion_cursor()
        self._dedo: tuple[float, float] | None = None   # punta filtrada (px cam)
        # Movimiento pendiente de aplicar (fraccion de encuadre). Sin el, los
        # gestos lentos se perderian frame a frame bajo la zona muerta.
        self._resto_x = 0.0
        self._resto_y = 0.0
        self._filtro_x = UnEuro(EURO_MINCUTOFF, EURO_BETA, EURO_DCUTOFF)
        self._filtro_y = UnEuro(EURO_MINCUTOFF, EURO_BETA, EURO_DCUTOFF)
        self._t_previo: float | None = None

    def reiniciar(self) -> None:
        """Suelta el enganche con el dedo (efecto embrague).

        La proxima llamada se re-anclara a donde este el cursor, de modo que
        recolocar la mano no provoca ningun salto.
        """
        self._dedo = None
        self._resto_x = self._resto_y = 0.0
        self._filtro_x.reiniciar()
        self._filtro_y.reiniciar()
        self._t_previo = None

    def actualizar(self, punta: tuple[float, float], ancho: int, alto: int,
                   mover: bool = True, dt: float | None = None) -> tuple[int, int]:
        """Desplaza el cursor segun cuanto se movio el dedo. Devuelve (x, y).

        Con `mover=False` se sigue el dedo pero el cursor se queda quieto: es lo
        que congela el puntero mientras haces clic, para que no se desplace por
        el propio gesto de juntar los dedos.

        `dt` (segundos desde el frame anterior) se mide solo, pero se puede
        inyectar para poder medir el filtro a una cadencia concreta en pruebas.
        """
        ahora = time.perf_counter()
        if self._dedo is None:               # primer frame: anclar al cursor real
            self._dedo = punta
            self._x, self._y = self.entrada.posicion_cursor()
            self._filtro_x.filtrar(punta[0] / ancho, dt or 1 / 30)
            self._filtro_y.filtrar(punta[1] / alto, dt or 1 / 30)
            self._t_previo = ahora
            return int(round(self._x)), int(round(self._y))

        # dt real: el filtro trabaja en segundos, asi que el tacto no cambia
        # aunque los FPS suban o bajen. Se acota para que un paron del sistema
        # (o el arranque) no produzca un dt absurdo.
        if dt is None:
            dt = recortar(ahora - (self._t_previo or ahora), 1 / 240, 0.2)
        self._t_previo = ahora

        # Desplazamiento bruto del dedo, en fraccion del encuadre (asi el tacto
        # no depende de la resolucion de la webcam).
        bruto_x = (punta[0] - self._dedo[0]) / ancho
        bruto_y = (punta[1] - self._dedo[1]) / alto
        vel = math.hypot(bruto_x, bruto_y)

        # Rechazo de saltos: un desplazamiento imposible en un frame es un glitch
        # o que MediaPipe cambio de mano. Se reancla a la nueva punta y no se
        # mueve el cursor, evitando el latigazo hacia la otra mano.
        if vel > SALTO_MAX:
            self._dedo = punta
            self._resto_x = self._resto_y = 0.0   # lo pendiente ya no vale
            self._filtro_x.reiniciar()
            self._filtro_y.reiniciar()
            self._filtro_x.filtrar(punta[0] / ancho, dt)
            self._filtro_y.filtrar(punta[1] / alto, dt)
            return int(round(self._x)), int(round(self._y))

        # Filtro One-Euro: quieto filtra fuerte (sin temblor), en movimiento
        # apenas filtra (sin retraso). El desplazamiento que mueve el cursor es
        # el de la senal YA filtrada.
        #
        # Se filtra en coordenadas NORMALIZADAS (fraccion del encuadre): el
        # corte del filtro depende de la velocidad, y en pixeles esa velocidad
        # seria el triple con una webcam de 1920 que con una de 640 para el
        # mismo gesto fisico -> cada camara filtraria distinto.
        sx = self._filtro_x.filtrar(punta[0] / ancho, dt) * ancho
        sy = self._filtro_y.filtrar(punta[1] / alto, dt) * alto
        fx = (sx - self._dedo[0]) / ancho
        fy = (sy - self._dedo[1]) / alto
        self._dedo = (sx, sy)

        if not mover:                     # congelado (clic): se descarta el gesto
            self._resto_x = self._resto_y = 0.0
            return int(round(self._x)), int(round(self._y))

        # El desplazamiento se ACUMULA en un residuo antes de aplicarse. Es lo
        # que permite mover el cursor despacio: un gesto lento reparte pocos
        # pixeles por frame y, sin este acumulador, cada uno caia bajo la zona
        # muerta y se perdia -> el cursor no se movia en absoluto por mucho que
        # arrastraras el dedo. El ruido aleatorio se cancela solo al sumarse.
        self._resto_x += fx
        self._resto_y += fy
        recorrido = math.hypot(self._resto_x, self._resto_y)
        if recorrido < ZONA_MUERTA:       # aun no da para un paso: guardar y salir
            return int(round(self._x)), int(round(self._y))

        fx, fy = self._resto_x, self._resto_y
        self._resto_x = self._resto_y = 0.0

        # Curva de ganancia: a baja velocidad solo PRECISION_PUNTERO de la
        # ganancia (control fino); a alta velocidad se suma la aceleracion para
        # cruzar la pantalla. El exponente hace que la subida sea suave al
        # principio y agresiva al final. Se mide con la velocidad instantanea
        # (`vel`), no con el residuo, para que acumular no parezca "ir rapido".
        factor = recortar(vel / VEL_ACEL_MAX, 0.0, 1.0) ** 1.5
        empuje = GANANCIA_PUNTERO * (
            PRECISION_PUNTERO + (1.0 - PRECISION_PUNTERO + ACELERACION) * factor)

        # De fraccion de encuadre a pixeles de pantalla. Cada eje se escala con
        # su propia dimension para alcanzar los bordes aunque la camara y la
        # pantalla no compartan relacion de aspecto.
        self._x = recortar(self._x + fx * empuje * self.entrada.ancho,
                           self.entrada.x0, self.entrada.x0 + self.entrada.ancho - 1)
        self._y = recortar(self._y + fy * empuje * self.entrada.alto,
                           self.entrada.y0, self.entrada.y0 + self.entrada.alto - 1)
        pos = (int(round(self._x)), int(round(self._y)))
        self.entrada.mover_cursor(*pos)
        return pos


class ControlClics:
    """Botones del raton a partir del gesto de la mano.

    - Dos dedos (indice + medio): mantiene pulsado el boton izquierdo. Un toque
      corto es un clic; si mantienes los dos dedos y mueves la mano, arrastras.
    - Mientras no te muevas lo suficiente el cursor se congela, para que el
      propio gesto de estirar el dedo no desplace el punto donde pulsas.
    """

    def __init__(self, entrada: EntradaWindows) -> None:
        self.entrada = entrada
        self._ancla: tuple[float, float] | None = None   # dedo al iniciar el clic
        self.arrastrando = False

    def actualizar_izquierdo(self, pulsando: bool, punta: tuple[float, float],
                             ancho: int) -> bool:
        """Sincroniza el boton izquierdo con el gesto. Devuelve si hay arrastre.

        `ancho` es el del encuadre y es obligatorio: el umbral de arrastre se
        mide como fraccion de el, para que se comporte igual con cualquier
        resolucion de webcam. Sin valor por defecto a proposito, porque uno
        equivocado convertiria cualquier temblor en un arrastre.
        """
        if pulsando:
            if self._ancla is None:          # acaba de empezar: pulsar
                self._ancla = punta
                self.arrastrando = False
                self.entrada.boton(derecho=False, presionar=True)
            elif not self.arrastrando:
                # Un movimiento claro convierte el clic en arrastre.
                if distancia(punta, self._ancla) / ancho > UMBRAL_ARRASTRE:
                    self.arrastrando = True
        else:
            self.soltar()
        return self.arrastrando

    def clic_derecho(self) -> None:
        self.entrada.clic(derecho=True)

    def soltar(self) -> None:
        """Suelta el boton si estaba pulsado. Idempotente y siempre seguro."""
        if self._ancla is not None:
            self._ancla = None
            self.arrastrando = False
        self.entrada.boton(derecho=False, presionar=False)


class ControlAtajos:
    """Dispara atajos de Windows a partir del gesto sostenido.

    Regla clave: UNA SOLA VEZ por gesto. Un atajo repetido seria desastroso
    (imagina un "cerrar ventana" repitiendose cada 0,3 s), asi que hay que
    soltar el gesto y volver a hacerlo para dispararlo de nuevo. Ademas exige
    mantenerlo `ESPERA_ATAJO` segundos, para que las formas por las que pasa la
    mano al abrirse o cerrarse no lancen nada.
    """

    def __init__(self, entrada: EntradaWindows, cfg: dict | None = None) -> None:
        self.entrada = entrada
        self.cfg = cfg                     # para resolver los atajos del usuario
        self._accion: str | None = None    # gesto de atajo en curso
        self._t0 = 0.0
        self._disparado = False
        self.ultimo = ""                   # informativo

    def reiniciar(self) -> None:
        self._accion = None
        self._disparado = False

    def actualizar(self, accion: str | None, aplicar: bool = True) -> str | None:
        """Devuelve el id del atajo lanzado en este frame, o None."""
        if accion != self._accion:         # cambio de gesto: rearmar
            self._accion = accion
            self._t0 = time.perf_counter()
            self._disparado = False
            return None

        if accion is None or self._disparado:
            return None
        if time.perf_counter() - self._t0 < ESPERA_ATAJO:
            return None

        self._disparado = True             # no se repite hasta soltar el gesto
        teclas = config.teclas_de(accion, self.cfg)
        if not teclas:
            return None
        self.ultimo = accion
        if aplicar:
            self.entrada.enviar_atajo(teclas)
        return accion


# --------------------------------------------------------------------------- #
# Dibujo sobre el frame de la camara
# --------------------------------------------------------------------------- #

def dibujar_esqueleto(frame, pts: list[tuple[float, float]], color) -> None:
    """Dibuja huesos y articulaciones de la mano con primitivas de OpenCV."""
    enteros = [(int(x), int(y)) for x, y in pts]
    for i, j in CONEXIONES:
        cv2.line(frame, enteros[i], enteros[j], (245, 245, 245), 2, cv2.LINE_AA)
    for p in enteros:
        cv2.circle(frame, p, 4, color, -1, cv2.LINE_AA)


def dibujar_puntero(frame, punta: tuple[float, float], color) -> None:
    """Diana sobre la punta del indice, como referencia en la vista de camara."""
    x, y = int(punta[0]), int(punta[1])
    cv2.circle(frame, (x, y), 14, color, 2, cv2.LINE_AA)
    cv2.circle(frame, (x, y), 3, color, -1, cv2.LINE_AA)


def dibujar_estela(frame, puntos, color) -> None:
    """Rastro del dedo en la vista de camara: se estrecha y apaga hacia atras."""
    if len(puntos) < 2:
        return
    n = len(puntos) - 1
    for i in range(n):
        t = (i + 1) / n                   # 1 = punta (el dedo), 0 = cola
        grosor = max(1, int(GROSOR_ESTELA * t))
        tono = tuple(int(c * (0.35 + 0.65 * t)) for c in color)
        cv2.line(frame, (int(puntos[i][0]), int(puntos[i][1])),
                 (int(puntos[i + 1][0]), int(puntos[i + 1][1])),
                 tono, grosor, cv2.LINE_AA)


# --------------------------------------------------------------------------- #
# Inicializacion
# --------------------------------------------------------------------------- #

def asegurar_modelo() -> Path:
    """Descarga `hand_landmarker.task` la primera vez que se ejecuta."""
    if MODELO.exists():
        return MODELO
    print(f"Descargando modelo en {MODELO} ...")
    temporal = MODELO.with_suffix(".parcial")
    urllib.request.urlretrieve(URL_MODELO, temporal)
    temporal.replace(MODELO)      # renombrado atomico: nada de archivos a medias
    print("Modelo listo.")
    return MODELO


def crear_detector() -> vision.HandLandmarker:
    """Construye el HandLandmarker en modo VIDEO (usa tracking entre frames)."""
    opciones = vision.HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(asegurar_modelo())),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=MAX_MANOS,
        min_hand_detection_confidence=CONF_DETECCION,
        min_hand_presence_confidence=CONF_PRESENCIA,
        min_tracking_confidence=CONF_SEGUIMIENTO,
    )
    return vision.HandLandmarker.create_from_options(opciones)


_SIN_CAMARA = (
    "No se encontro ninguna camara que funcione.\n"
    "- Revisa Configuracion > Privacidad > Camara y permite el acceso a las "
    "aplicaciones de escritorio.\n"
    "- Si otra app la tiene en EXCLUSIVA (apps antiguas), cierrala; con Zoom o "
    "Teams (que comparten via Windows) no deberia hacer falta.\n"
    "- Si tienes varias camaras, fija INDICE_CAMARA a mano en el codigo."
)

RUTA_PREF_CAMARA = carpeta_base() / "config_camara.json"


def abrir_camara() -> cv2.VideoCapture:
    """Detecta las camaras, deja elegir en un menu y abre la elegida.

    - `INDICE_CAMARA` fijado a mano se abre directo, sin detectar ni preguntar.
    - Una preferencia guardada valida se reutiliza sin molestar.
    - Con varias camaras (o `MENU_CAMARA_SIEMPRE`) se abre el menu con miniaturas.
    """
    orden = camara.backends(COMPARTIR_CAMARA)

    # Atajos que evitan explorar todas las camaras (mas rapido al arrancar).
    if INDICE_CAMARA is not None:
        cap, backend = camara.abrir(INDICE_CAMARA, ANCHO, ALTO, orden)
        if cap is not None:
            print(f"Camara {INDICE_CAMARA} ({camara.nombre_backend(backend)}).")
            return cap
        raise SystemExit(f"La camara fijada (INDICE_CAMARA={INDICE_CAMARA}) no "
                         f"responde.\n{_SIN_CAMARA}")

    guardado = camara.cargar_preferencia(RUTA_PREF_CAMARA)
    if guardado is not None and not MENU_CAMARA_SIEMPRE:
        cap, backend = camara.abrir(guardado, ANCHO, ALTO, orden)
        if cap is not None:
            print(f"Camara {guardado} recordada ({camara.nombre_backend(backend)}).")
            return cap
        # La camara guardada ya no esta: se ignora y se detecta de nuevo.

    print("Detectando camaras...")
    camaras = camara.listar(ANCHO, ALTO, orden, CAMARAS_A_PROBAR)
    if not camaras:
        raise SystemExit(_SIN_CAMARA)
    for c in camaras:
        print(f"  [{c.indice}] {c.nombre}  {c.ancho}x{c.alto}  "
              f"{camara.nombre_backend(c.backend)}")

    indice, recordar = camara.elegir_indice(
        camaras, forzado=None, guardado=guardado,
        menu_siempre=MENU_CAMARA_SIEMPRE, dialogo=camara.menu_grafico)
    if indice is None:
        raise SystemExit("No se eligio ninguna camara.")
    if recordar:
        camara.guardar_preferencia(RUTA_PREF_CAMARA, indice)

    cap, backend = camara.abrir(indice, ANCHO, ALTO, orden)
    if cap is None:
        raise SystemExit(_SIN_CAMARA)
    print(f"Usando camara {indice} ({camara.nombre_backend(backend)}).")
    return cap


# --------------------------------------------------------------------------- #
# Programa principal
# --------------------------------------------------------------------------- #

def aplicar_config(cfg: dict) -> dict:
    """Vuelca la configuracion del launcher en los ajustes de la deteccion.

    La sensibilidad y las preferencias de camara son globales del modulo (las
    leen `ControlPuntero` y `abrir_camara`), asi que se sobreescriben aqui.
    Devuelve el mapa forma -> accion.
    """
    global GANANCIA_PUNTERO, ACELERACION
    global INDICE_CAMARA, COMPARTIR_CAMARA, MENU_CAMARA_SIEMPRE

    GANANCIA_PUNTERO = cfg["sensibilidad"]["ganancia"]
    ACELERACION = cfg["sensibilidad"]["aceleracion"]
    INDICE_CAMARA = cfg["camara"]["indice"]
    COMPARTIR_CAMARA = cfg["camara"]["compartir"]
    MENU_CAMARA_SIEMPRE = cfg["camara"]["menu_siempre"]
    return dict(cfg["gestos"])


def main(cfg: dict | None = None) -> None:
    if cfg is None:
        cfg = config.cargar(carpeta_base() / config.RUTA_DEFECTO_NOMBRE)
    mapa = aplicar_config(cfg)     # forma de la mano -> accion elegida

    cap = abrir_camara()          # lanza SystemExit con ayuda si no hay ninguna

    entrada = EntradaWindows(simular=SIMULAR_ENTRADA)
    puntero = ControlPuntero(entrada)
    atajos = ControlAtajos(entrada, cfg)
    clics = ControlClics(entrada)
    estela_camara: deque[tuple[float, float]] = deque(maxlen=LARGO_ESTELA)

    accion_control = AccionSostenida(ALTERNAR, ESPERA_CONTROL)
    accion_clic_der = AccionSostenida(CLIC_DER, ESTABILIDAD_CLIC_DER)

    suavizadores = [SuavizadorGesto() for _ in range(MAX_MANOS)]
    control = CONTROL_ACTIVO
    t_inicio = time.perf_counter()

    try:
        with crear_detector() as detector:
            while True:
                ok, frame = cap.read()
                if not ok:
                    print("Frame no valido; se corta la captura.")
                    break

                frame = cv2.flip(frame, 1)      # efecto espejo
                alto, ancho = frame.shape[:2]

                # --- Inferencia ------------------------------------------- #
                imagen_entrada = frame
                if ESCALA_DETECCION < 1.0:
                    imagen_entrada = cv2.resize(frame, None,
                                                fx=ESCALA_DETECCION,
                                                fy=ESCALA_DETECCION,
                                                interpolation=cv2.INTER_AREA)

                imagen = mp.Image(
                    image_format=mp.ImageFormat.SRGB,
                    data=cv2.cvtColor(imagen_entrada, cv2.COLOR_BGR2RGB))
                # El modo VIDEO exige marcas de tiempo estrictamente crecientes.
                ts_ms = int((time.perf_counter() - t_inicio) * 1000)
                resultado = detector.detect_for_video(imagen, ts_ms)

                # --- Clasificacion: forma -> accion segun la config -------- #
                # Solo se dibuja el esqueleto; ninguna indicacion escrita.
                accion_principal = NADA
                pts_principal = None            # landmarks de la primera mano

                if resultado.hand_landmarks:
                    for i, landmarks in enumerate(resultado.hand_landmarks):
                        pts = a_pixeles(landmarks, ancho, alto)
                        forma = clasificar_gesto(dedos_extendidos(pts), pts)
                        if i < len(suavizadores):
                            forma = suavizadores[i].actualizar(forma)
                        accion = mapa.get(forma, NADA)
                        if i == 0:
                            accion_principal, pts_principal = accion, pts
                        color_mano = (COLOR_ACCION.get(accion) or COLOR_ATAJO)
                        dibujar_esqueleto(frame, pts, color_mano)
                else:
                    for s in suavizadores:
                        s.actualizar(DESCONOCIDO)

                # --- Acciones mantenidas: on/off y clic derecho ------------- #
                if accion_control.actualizar(accion_principal)[0]:
                    control = not control
                    puntero.reiniciar()
                    atajos.reiniciar()
                    clics.soltar()

                # El clic derecho se mantiene un instante para que el paso fugaz
                # por esa forma al abrir o cerrar la mano no dispare un clic.
                if accion_clic_der.actualizar(accion_principal)[0] and control:
                    clics.clic_derecho()

                # --- Puntero, clics y atajos segun la accion ---------------- #
                # Cualquier accion que no gestione la app es un atajo de Windows
                es_atajo = accion_principal not in ACCIONES_APP

                if not control or pts_principal is None:
                    puntero.reiniciar()
                    atajos.reiniciar()
                    clics.soltar()          # nunca dejar el boton hundido
                    estela_camara.clear()

                elif accion_principal in ACCIONES_PUNTERO:
                    atajos.reiniciar()
                    pulsando = accion_principal == CLIC_IZQ
                    punta = pts_principal[INDICE_TIP]

                    # Con el boton pulsado el cursor se congela (clic limpio)
                    # hasta que muevas lo suficiente: entonces pasa a arrastrar.
                    arrastrando = clics.actualizar_izquierdo(pulsando, punta, ancho)
                    pos = puntero.actualizar(punta, ancho, alto,
                                             mover=not pulsando or arrastrando)

                    color = COLOR_ACCION[accion_principal]
                    estela_camara.append(punta)
                    dibujar_estela(frame, estela_camara, color)
                    dibujar_puntero(frame, punta, color)

                elif es_atajo:
                    # Al soltar el gesto de apuntar, el cursor se queda donde
                    # este (embrague).
                    puntero.reiniciar()
                    clics.soltar()
                    estela_camara.clear()
                    atajos.actualizar(accion_principal)
                else:
                    puntero.reiniciar()
                    atajos.reiniciar()
                    clics.soltar()
                    estela_camara.clear()

                cv2.imshow(NOMBRE_VENTANA, frame)

                # Salir: tecla q/ESC o el boton X de la ventana.
                tecla = cv2.waitKey(1) & 0xFF
                if tecla in (ord("q"), 27):     # 'q' o ESC
                    break
                if cv2.getWindowProperty(NOMBRE_VENTANA,
                                         cv2.WND_PROP_VISIBLE) < 1:
                    break
                if tecla == ord("c"):
                    control = not control
                    puntero.reiniciar()
                    atajos.reiniciar()
                    clics.soltar()
    finally:
        entrada.soltar_todo()     # botones y modificadores, nunca hundidos
        cap.release()
        cv2.destroyAllWindows()


def autocomprobacion() -> int:
    """Verifica que el modelo carga y el detector procesa un frame en blanco.

    Sirve para validar un .exe empaquetado sin necesidad de camara:
        gestos_manos.exe --selftest
    Devuelve 0 si todo va bien.
    """
    import numpy as np

    print("Carpeta base:", carpeta_base())
    print("Modelo:", MODELO, "existe:" , MODELO.exists())
    detector = crear_detector()
    imagen = mp.Image(image_format=mp.ImageFormat.SRGB,
                      data=np.zeros((ALTO, ANCHO, 3), np.uint8))
    detector.detect_for_video(imagen, 0)
    detector.close()
    print("OK: mediapipe cargo el modelo y proceso un frame.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(autocomprobacion())
    main()
