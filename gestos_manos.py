"""
Detector de gestos de mano en tiempo real (MediaPipe Tasks + OpenCV).

Todo se maneja con las manos; las teclas son solo un respaldo. El cursor del
raton se mueve, pero no se envian clics.

Gestos:
    - Apuntando (solo indice)
        mueve el CURSOR REAL de Windows de forma RELATIVA, como un trackpad:
        la mano lo empuja segun cuanto se mueva; al bajar la mano y volver a
        apuntar, continua desde donde se quedo (embrague)
    - Mano abierta -> ACERCAR (zoom in) de forma sostenida
    - Puno         -> ALEJAR  (zoom out) de forma sostenida
        el zoom se envia como Ctrl + '+' / Ctrl + '-' a la ventana seleccionada
    - Pulgar arriba -> mantenido 1,2 s: activa / desactiva el control
    - Paz           -> mantenido 2 s: salir del programa

Uso:
    python gestos_manos.py

Teclas (respaldo, requieren que la ventana de la camara tenga el foco):
    q / ESC -> salir          c -> activar/desactivar el control
    f       -> panel de FPS   s -> suavizado temporal del gesto

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

from control_windows import EntradaWindows

# --------------------------------------------------------------------------- #
# Configuracion
# --------------------------------------------------------------------------- #

INDICE_CAMARA = 0          # 0 = webcam por defecto
ANCHO, ALTO = 960, 540     # resolucion de captura solicitada a la camara
NOMBRE_VENTANA = "Detector de gestos - MediaPipe"
MAX_MANOS = 2              # bajar a 1 da unos FPS extra
CONF_DETECCION = 0.6
CONF_PRESENCIA = 0.5
CONF_SEGUIMIENTO = 0.5

# La inferencia se hace sobre una copia reducida del frame; los landmarks son
# normalizados (0..1), asi que se dibujan igual sobre el frame a tamano completo.
# 1.0 = sin reduccion; 0.5-0.7 acelera bastante con poca perdida de precision.
ESCALA_DETECCION = 0.6

VENTANA_SUAVIZADO = 5      # nº de frames para el voto mayoritario del gesto

# --- Control por gestos ---------------------------------------------------- #
CONTROL_ACTIVO = True      # estado inicial del puntero y el zoom
SIMULAR_ENTRADA = False    # True = solo imprime las acciones, no toca el sistema
ZOOM_NUMERICO = False      # True = usar el +/- del teclado numerico

# Gestos mantenidos para las acciones globales:
ESPERA_CONTROL = 1.2       # segundos de PULGAR ARRIBA para activar/desactivar
ESPERA_SALIR = 2.0         # segundos de PAZ para salir

# --- Puntero relativo (tipo raton / trackpad) ------------------------------ #
# El puntero se desplaza segun cuanto muevas la mano, no segun donde este; al
# bajar la mano y volver a apuntar continua desde donde se quedo (como levantar
# un raton para recolocarlo). No hay recuadro fijo que mapear.
GANANCIA_PUNTERO = 3.2     # px de pantalla por cada px que se mueve el dedo
ACELERACION = 0.9          # empuje extra en gestos rapidos (0 = velocidad constante)
VEL_ACEL_MAX = 45.0        # px/frame del dedo donde la aceleracion llega al tope
SUAVIZADO_DEDO = 0.5       # EMA de la punta antes de medir el desplazamiento
ZONA_MUERTA = 0.6          # px del dedo por debajo de los cuales no se mueve nada

LARGO_ESTELA = 26          # posiciones que deja el rastro del dedo (0 = sin estela)
GROSOR_ESTELA = 7          # grosor del trazo en la punta

# --- Zoom por abrir / cerrar la mano --------------------------------------- #
# Mano abierta = acercar, puno = alejar. Mientras mantengas el gesto se van
# enviando clics de Ctrl + '+' / '-' a la ventana seleccionada a este ritmo.
ZOOM_INTERVALO = 0.30      # segundos entre clics de zoom mientras se mantiene

# Modelo: variante float16 (rapida). Para mas precision usar la ruta ".../full/..."
MODELO = carpeta_base() / "hand_landmarker.task"
URL_MODELO = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)

# Umbrales de la heuristica (normalizados por el tamano de la mano)
ANG_DEDO_EXTENDIDO = 155.0  # grados en la articulacion PIP
ANG_PULGAR_RECTO = 150.0    # grados en la articulacion IP del pulgar
SEP_MIN_PAZ = 0.35          # separacion minima entre puntas indice-medio
ALTURA_MIN_PULGAR = 0.35    # cuanto debe subir el pulgar sobre la muneca

# --------------------------------------------------------------------------- #
# Etiquetas de gesto y colores
# --------------------------------------------------------------------------- #

PUNO = "PUNO"
MANO_ABIERTA = "MANO ABIERTA"
PAZ = "PAZ"
PULGAR_ARRIBA = "PULGAR ARRIBA"
APUNTANDO = "APUNTANDO"
DESCONOCIDO = "---"

# Mano abierta = acercar, puno = alejar (usado por el control de zoom)
DIR_ZOOM = {MANO_ABIERTA: +1, PUNO: -1}

COLORES = {                 # BGR, para dibujar sobre el frame de OpenCV
    PUNO: (60, 60, 235),
    MANO_ABIERTA: (60, 200, 60),
    PAZ: (235, 180, 40),
    PULGAR_ARRIBA: (40, 200, 235),
    APUNTANDO: (220, 90, 220),
    DESCONOCIDO: (170, 170, 170),
}

# --------------------------------------------------------------------------- #
# Indices de landmarks (mapa de 21 puntos de MediaPipe Hands)
# --------------------------------------------------------------------------- #

MUNECA = 0
PULGAR_MCP, PULGAR_IP, PULGAR_TIP = 2, 3, 4
INDICE_TIP = 8
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
    """Traduce el patron de dedos extendidos a un nombre de gesto."""
    pulgar, indice, medio, anular, menique = dedos
    escala = escala_mano(pts)

    if not any(dedos):
        return PUNO

    if all(dedos):
        return MANO_ABIERTA

    # Paz: indice y medio extendidos y separados (el pulgar es indiferente).
    if indice and medio and not anular and not menique:
        separacion = distancia(pts[INDICE_TIP], pts[MEDIO_TIP]) / escala
        return PAZ if separacion > SEP_MIN_PAZ else DESCONOCIDO

    # Pulgar arriba: solo el pulgar extendido y apuntando hacia arriba.
    # En imagen la Y crece hacia abajo, de ahi la comparacion invertida.
    if pulgar and not (indice or medio or anular or menique):
        if pts[PULGAR_TIP][1] < pts[MUNECA][1] - ALTURA_MIN_PULGAR * escala:
            return PULGAR_ARRIBA
        return DESCONOCIDO

    # Apuntar: solo el indice entre los dedos largos (el pulgar es indiferente,
    # asi funciona tanto con el indice solo como en forma de "L").
    if indice and not (medio or anular or menique):
        return APUNTANDO

    return DESCONOCIDO


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
        self._dedo: tuple[float, float] | None = None   # punta suavizada (px cam)

    def reiniciar(self) -> None:
        """Suelta el enganche con el dedo (efecto embrague).

        La proxima llamada se re-anclara a donde este el cursor, de modo que
        recolocar la mano no provoca ningun salto.
        """
        self._dedo = None

    def actualizar(self, punta: tuple[float, float],
                   ancho: int, alto: int) -> tuple[int, int]:
        """Desplaza el cursor segun cuanto se movio el dedo. Devuelve (x, y)."""
        if self._dedo is None:               # primer frame: anclar al cursor real
            self._dedo = punta
            self._x, self._y = self.entrada.posicion_cursor()
            return int(round(self._x)), int(round(self._y))

        # Suavizado ligero de la punta para quitar temblor sin anadir retraso.
        sx = self._dedo[0] + (punta[0] - self._dedo[0]) * SUAVIZADO_DEDO
        sy = self._dedo[1] + (punta[1] - self._dedo[1]) * SUAVIZADO_DEDO
        dx, dy = sx - self._dedo[0], sy - self._dedo[1]
        self._dedo = (sx, sy)

        recorrido = math.hypot(dx, dy)
        if recorrido < ZONA_MUERTA:          # mano casi quieta: no mover
            return int(round(self._x)), int(round(self._y))

        # Aceleracion: los gestos rapidos avanzan mas por px (control fino en
        # lento, alcance en rapido), como la aceleracion del raton de Windows.
        empuje = GANANCIA_PUNTERO * (
            1.0 + ACELERACION * recortar(recorrido / VEL_ACEL_MAX, 0.0, 1.0))
        self._x = recortar(self._x + dx * empuje,
                           self.entrada.x0, self.entrada.x0 + self.entrada.ancho - 1)
        self._y = recortar(self._y + dy * empuje,
                           self.entrada.y0, self.entrada.y0 + self.entrada.alto - 1)
        pos = (int(round(self._x)), int(round(self._y)))
        self.entrada.mover_cursor(*pos)
        return pos


class ControlZoom:
    """Zoom por abrir/cerrar la mano: Ctrl + '+' con la palma, Ctrl + '-' con el puno.

    Mientras se mantiene el gesto se emite un clic al empezar y luego uno cada
    `ZOOM_INTERVALO` segundos, de forma sostenida. Cambiar de mano abierta a
    puno invierte el sentido al instante.
    """

    def __init__(self, entrada: EntradaWindows) -> None:
        self.entrada = entrada
        self._dir = 0                      # -1 alejar, 0 nada, +1 acercar
        self._t_ultimo = 0.0
        self.acumulado = 0                 # solo informativo, para el HUD

    def reiniciar(self) -> None:
        self._dir = 0

    def actualizar(self, direccion: int, aplicar: bool = True) -> int:
        """direccion: +1 mano abierta, -1 puno, 0 ninguno. Devuelve el clic emitido."""
        if direccion == 0:
            self._dir = 0
            return 0

        ahora = time.perf_counter()
        if direccion != self._dir:         # gesto recien iniciado o sentido nuevo
            self._dir = direccion
            self._t_ultimo = ahora
            emitido = direccion            # primer clic inmediato: respuesta viva
        elif ahora - self._t_ultimo >= ZOOM_INTERVALO:
            self._t_ultimo = ahora
            emitido = direccion
        else:
            return 0

        self.acumulado += emitido
        if aplicar:
            self.entrada.zoom(emitido)
        return emitido


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


def dibujar_progreso(frame, texto: str, progreso: float, color) -> None:
    """Barra inferior que muestra cuanto llevas manteniendo un gesto."""
    alto, ancho = frame.shape[:2]
    x0, x1 = ancho // 4, ancho - ancho // 4
    y = alto - 46
    cv2.rectangle(frame, (x0, y), (x1, y + 18), (40, 40, 40), -1)
    cv2.rectangle(frame, (x0, y), (int(x0 + (x1 - x0) * progreso), y + 18),
                  color, -1)
    cv2.rectangle(frame, (x0, y), (x1, y + 18), (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(frame, texto, (x0, y - 8), cv2.FONT_HERSHEY_SIMPLEX,
                0.6, color, 2, cv2.LINE_AA)


def dibujar_panel(frame, lineas: list[tuple[str, tuple[int, int, int]]],
                  x: int = 12, y: int = 12) -> None:
    """Dibuja un recuadro semitransparente con varias lineas de texto."""
    if not lineas:
        return

    alto_linea = 30
    ancho_panel = 20 + max(
        cv2.getTextSize(t, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0][0]
        for t, _ in lineas
    )
    alto_panel = 16 + alto_linea * len(lineas)

    # addWeighted solo sobre la region del panel: mucho mas barato que
    # componer el frame completo.
    roi = frame[y:y + alto_panel, x:x + ancho_panel]
    if roi.size:
        oscuro = roi.copy()
        oscuro[:] = (25, 25, 25)
        cv2.addWeighted(oscuro, 0.55, roi, 0.45, 0, roi)

    for i, (texto, color) in enumerate(lineas):
        cv2.putText(frame, texto, (x + 10, y + 30 + i * alto_linea),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)


def etiqueta_en_mano(frame, pts, texto: str, color) -> None:
    """Escribe el gesto justo encima de la mano detectada."""
    x = int(min(p[0] for p in pts))
    y = int(min(p[1] for p in pts)) - 12
    x = max(5, min(x, frame.shape[1] - 260))
    y = max(24, y)
    cv2.putText(frame, texto, (x, y), cv2.FONT_HERSHEY_SIMPLEX,
                0.8, (0, 0, 0), 4, cv2.LINE_AA)   # borde para legibilidad
    cv2.putText(frame, texto, (x, y), cv2.FONT_HERSHEY_SIMPLEX,
                0.8, color, 2, cv2.LINE_AA)


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


def abrir_camara() -> cv2.VideoCapture:
    """Abre la webcam con el backend DirectShow (arranque rapido en Windows)."""
    cap = cv2.VideoCapture(INDICE_CAMARA, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, ANCHO)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, ALTO)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # menos latencia: no acumular frames
    return cap


# --------------------------------------------------------------------------- #
# Programa principal
# --------------------------------------------------------------------------- #

def main() -> None:
    cap = abrir_camara()
    if not cap.isOpened():
        raise SystemExit(
            "No se pudo abrir la camara. Revisa que no la este usando otra "
            "aplicacion y los permisos en Configuracion > Privacidad > Camara."
        )

    entrada = EntradaWindows(simular=SIMULAR_ENTRADA,
                             teclado_numerico=ZOOM_NUMERICO)
    puntero = ControlPuntero(entrada)
    zoom = ControlZoom(entrada)
    estela_camara: deque[tuple[float, float]] = deque(maxlen=LARGO_ESTELA)

    accion_control = AccionSostenida(PULGAR_ARRIBA, ESPERA_CONTROL)
    accion_salir = AccionSostenida(PAZ, ESPERA_SALIR)

    suavizadores = [SuavizadorGesto() for _ in range(MAX_MANOS)]
    control = CONTROL_ACTIVO
    mostrar_panel = True
    suavizar = True

    fps = 0.0
    t_previo = time.perf_counter()
    t_inicio = t_previo

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

                # --- Dibujo y clasificacion -------------------------------- #
                lineas = []
                gesto_principal = DESCONOCIDO
                pts_principal = None            # landmarks de la primera mano

                if resultado.hand_landmarks:
                    for i, landmarks in enumerate(resultado.hand_landmarks):
                        pts = a_pixeles(landmarks, ancho, alto)
                        gesto = clasificar_gesto(dedos_extendidos(pts), pts)
                        if suavizar and i < len(suavizadores):
                            gesto = suavizadores[i].actualizar(gesto)
                        if i == 0:
                            gesto_principal, pts_principal = gesto, pts

                        color = COLORES[gesto]
                        dibujar_esqueleto(frame, pts, color)
                        etiqueta_en_mano(frame, pts, gesto, color)

                        # Como la imagen esta en espejo, la etiqueta de MediaPipe
                        # coincide con la mano real del usuario.
                        lado = "?"
                        if i < len(resultado.handedness):
                            lado = ("Izq" if resultado.handedness[i][0].category_name
                                    == "Left" else "Der")
                        lineas.append((f"Mano {lado}: {gesto}", color))
                else:
                    for s in suavizadores:
                        s.actualizar(DESCONOCIDO)
                    lineas.append(("Sin manos detectadas", COLORES[DESCONOCIDO]))

                # --- Gestos mantenidos: encender/apagar y salir ------------- #
                disparo_control, prog_control = accion_control.actualizar(
                    gesto_principal)
                disparo_salir, prog_salir = accion_salir.actualizar(
                    gesto_principal)

                if disparo_control:
                    control = not control
                    puntero.reiniciar()
                    zoom.reiniciar()
                if disparo_salir:
                    break

                if prog_control > 0:
                    dibujar_progreso(
                        frame,
                        f"Pulgar: {'desactivar' if control else 'activar'} control",
                        prog_control, COLORES[PULGAR_ARRIBA])
                elif prog_salir > 0:
                    dibujar_progreso(frame, "Paz: salir", prog_salir, COLORES[PAZ])

                # --- Puntero (apuntar) y zoom (abrir/cerrar la mano) -------- #
                direccion_zoom = DIR_ZOOM.get(gesto_principal, 0)

                if not control or pts_principal is None:
                    puntero.reiniciar()
                    zoom.reiniciar()
                    estela_camara.clear()

                elif gesto_principal == APUNTANDO:
                    zoom.reiniciar()
                    # Mueve el cursor real de Windows segun el desplazamiento del
                    # dedo; la estela y la diana son la referencia en la camara.
                    pos = puntero.actualizar(pts_principal[INDICE_TIP], ancho, alto)
                    estela_camara.append(pts_principal[INDICE_TIP])
                    dibujar_estela(frame, estela_camara, COLORES[APUNTANDO])
                    dibujar_puntero(frame, pts_principal[INDICE_TIP],
                                    COLORES[APUNTANDO])
                    lineas.append((f"Cursor: {pos[0]}, {pos[1]}",
                                   COLORES[APUNTANDO]))

                elif direccion_zoom != 0:
                    # Al soltar el gesto de apuntar, el cursor se queda donde
                    # este (embrague).
                    puntero.reiniciar()
                    estela_camara.clear()

                    # El zoom va a la ventana en primer plano: si esa ventana es
                    # la de la camara, no tiene sentido enviarlo.
                    objetivo = entrada.titulo_ventana_activa()
                    propia = objetivo == NOMBRE_VENTANA
                    zoom.actualizar(direccion_zoom, aplicar=not propia)
                    accion = "ACERCAR" if direccion_zoom > 0 else "ALEJAR"
                    if propia:
                        lineas.append(("Selecciona la ventana a ampliar",
                                       (60, 200, 235)))
                    else:
                        lineas.append(
                            (f"Zoom {accion} (x{zoom.acumulado:+d}) -> "
                             f"{objetivo[:22] or '?'}", COLORES[MANO_ABIERTA]))
                else:
                    puntero.reiniciar()
                    zoom.reiniciar()
                    estela_camara.clear()

                # --- FPS (media exponencial para que no baile) -------------- #
                ahora = time.perf_counter()
                dt = ahora - t_previo
                t_previo = ahora
                if dt > 0:
                    fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps else 1.0 / dt

                if mostrar_panel:
                    lineas.append(
                        (f"Control: {'ON' if control else 'OFF'}  (pulgar 1,2 s)",
                         (60, 220, 60) if control else (100, 100, 100)))
                    lineas.append(("indice=puntero  abrir=acercar  cerrar=alejar",
                                   (180, 180, 180)))
                    lineas.append((f"FPS: {fps:4.1f}", (240, 240, 240)))
                    lineas.append(("paz 2 s = salir", (170, 170, 170)))
                    dibujar_panel(frame, lineas)

                cv2.imshow(NOMBRE_VENTANA, frame)

                # Teclas de respaldo (solo con el foco en esta ventana)
                tecla = cv2.waitKey(1) & 0xFF
                if tecla in (ord("q"), 27):     # 'q' o ESC
                    break
                if tecla == ord("c"):
                    control = not control
                    puntero.reiniciar()
                    zoom.reiniciar()
                if tecla == ord("f"):
                    mostrar_panel = not mostrar_panel
                if tecla == ord("s"):
                    suavizar = not suavizar
    finally:
        entrada.soltar_todo()     # nunca dejar Ctrl pulsado al salir
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
