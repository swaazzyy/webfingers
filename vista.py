"""
Vista previa de la camara dentro de la ventana principal, como el preview de OBS.

Antes, para ver que estaba captando la camara habia que arrancar la deteccion y
mirar una ventana aparte de OpenCV. Encuadrarse, comprobar la luz o elegir la
camara buena eran cosas que no se podian hacer desde la ventana de la app.

El panel tiene DOS fuentes y cambia sola segun lo que este pasando:

    - con la deteccion PARADA abre la camara el mismo, para que puedas
      encuadrarte antes de empezar;
    - con la deteccion EN MARCHA no toca la camara (la tiene el otro proceso) y
      enseña los frames que ese proceso publica ya dibujados, con el esqueleto,
      la mira y el HUD incluidos.

El cambio de una a otra tiene que ser limpio: en Windows una camara normal no
se puede abrir dos veces, asi que soltarla ANTES de lanzar la deteccion no es un
detalle de orden, es la diferencia entre que arranque o que falle diciendo que
no hay camara.

La lectura va en un hilo aparte. `VideoCapture.read()` se bloquea hasta que hay
imagen, y llamarlo desde el hilo de Tk congelaria la ventana entera entre frame
y frame.
"""

from __future__ import annotations

import threading
import tkinter as tk

import cv2
from PIL import Image, ImageTk

import camara

# Grises del panel, a juego con el HUD (que copia los de OBS).
FONDO = "#1b1b1b"
BORDE = "#3f3f3f"
CABECERA = "#2b2b2b"
TEXTO = "#d8d8d8"
TENUE = "#8a8a8a"
VIVO = "#5ac85a"
PARADO = "#6b7280"

PERIODO_MS = 33          # ~30 frames por segundo, que es lo que da la camara


class VistaPrevia:
    """Panel con la imagen de la camara y una cabecera tipo dock de OBS."""

    def __init__(self, padre, t, ancho: int = 396, alto: int = 223) -> None:
        self.t = t                          # traductor de idiomas.py
        self.ancho, self.alto = ancho, alto

        self.marco = tk.Frame(padre, bd=1, relief="solid",
                              highlightthickness=0)
        # Cabecera sin ningun punto de estado: aqui no se graba nada, y un
        # circulito al lado del titulo se lee como un indicador de grabacion.
        # Si la deteccion esta en marcha o no ya lo dice el pie de la ventana.
        cab = tk.Frame(self.marco, bg=CABECERA)
        cab.pack(fill="x")
        self.titulo = tk.Label(cab, text=self._txt("vista_titulo"), bg=CABECERA,
                               fg=TENUE, font=("Segoe UI", 8, "bold"))
        self.titulo.pack(side="left", padx=(9, 0), pady=3)
        self.info = tk.Label(cab, text="", bg=CABECERA, fg=TENUE,
                             font=("Segoe UI", 8))
        self.info.pack(side="right", padx=8, pady=3)

        # La caja fija el tamano del panel y el lienzo va dentro, centrado. Es
        # la unica forma de que no baile: en un Label, `width` y `height` se
        # miden en CARACTERES cuando enseña texto y en PIXELES cuando enseña una
        # imagen, asi que dejandolo a su aire la ventana entera daba un salto en
        # cuanto llegaba el primer frame.
        self.caja = tk.Frame(self.marco, width=ancho, height=alto, bg=FONDO)
        self.caja.pack_propagate(False)
        self.caja.pack()
        self.lienzo = tk.Label(self.caja, bg=FONDO, fg=TENUE,
                               font=("Segoe UI", 9))
        self.lienzo.pack(expand=True)

        self._imagen = None                 # referencia viva: si se pierde,
        #                                     Tk descarta el frame y sale negro
        self._cap = None
        self._hilo: threading.Thread | None = None
        self._parar = threading.Event()
        self._lock = threading.Lock()
        self._ultimo = None                 # frame crudo de la camara
        self._receptor = None               # puente con la deteccion
        self._tarea = None                  # id del after() de Tk
        self._pausada = False               # ventana minimizada
        self._aviso = ""
        self._mostrar_aviso(self._txt("vista_parada"))

    # --- Textos ------------------------------------------------------------ #

    def _txt(self, clave: str) -> str:
        return self.t(clave) if self.t is not None else clave

    def retraducir(self, t) -> None:
        self.t = t
        self.titulo.configure(text=self._txt("vista_titulo"))
        if self._aviso:
            self._mostrar_aviso(self._aviso_clave)

    # --- Estado visible ---------------------------------------------------- #

    def _mostrar_aviso(self, texto: str, clave: str = "vista_parada") -> None:
        """Deja el panel en negro con un mensaje, como el preview vacio de OBS."""
        self._aviso = texto
        self._aviso_clave = clave
        self._imagen = None
        self.lienzo.configure(image="", text=texto)

    def _pintar(self, frame) -> None:
        """Escala el frame al panel y lo dibuja."""
        alto, ancho = frame.shape[:2]
        escala = min(self.ancho / ancho, self.alto / alto)
        destino = (max(1, int(ancho * escala)), max(1, int(alto * escala)))
        pequeno = cv2.resize(frame, destino, interpolation=cv2.INTER_AREA)
        imagen = Image.fromarray(cv2.cvtColor(pequeno, cv2.COLOR_BGR2RGB))
        self._imagen = ImageTk.PhotoImage(imagen)
        self._aviso = ""
        self.lienzo.configure(image=self._imagen, text="")
        self.info.configure(text=f"{ancho}x{alto}")

    def marcar(self, vivo: bool) -> None:
        """Compatibilidad: el estado se ve en el pie, aqui ya no hay indicador."""

    def aplicar_tema(self, tema: dict) -> None:
        """El panel se queda oscuro siempre (es una imagen), solo el borde cambia."""
        self.marco.configure(bg=tema["borde"], highlightbackground=tema["borde"])

    # --- Fuente 1: la camara, con la deteccion parada ---------------------- #

    def arrancar_camara(self, cfg: dict, ruta_pref) -> None:
        """Abre la camara para previsualizar. No hace nada si ya esta abierta."""
        if self._hilo is not None or self._receptor is not None:
            return
        # Abrir la camara puede tardar MUCHO (con el backend compartido de
        # Windows, hasta 20 s en algunos equipos), asi que hay que decirlo: un
        # panel que sigue diciendo "apagada" durante veinte segundos parece
        # roto, y el usuario acaba pulsando cosas.
        self._mostrar_aviso(self._txt("vista_esperando"), "vista_esperando")
        self._parar.clear()
        self._hilo = threading.Thread(target=self._leer_camara,
                                      args=(dict(cfg), ruta_pref), daemon=True)
        self._hilo.start()
        self._programar()

    def _leer_camara(self, cfg: dict, ruta_pref) -> None:
        """Hilo lector: abre la camara y va dejando el ultimo frame."""
        ancho, alto = (int(v) for v in cfg["deteccion"]["resolucion"].split("x"))
        orden = camara.backends(cfg["camara"]["compartir"])
        indice = cfg["camara"]["indice"]
        if indice is None:
            indice = camara.cargar_preferencia(ruta_pref)
        if indice is None:
            indice = 0                      # la primera; solo es para mirarse
        cap, _ = camara.abrir(indice, ancho, alto, orden)
        if cap is None:
            with self._lock:
                self._ultimo = False        # False = no se pudo abrir
            return
        self._cap = cap
        try:
            while not self._parar.is_set():
                ok, frame = cap.read()
                if not ok:
                    break
                if cfg["deteccion"]["espejo"]:
                    frame = cv2.flip(frame, 1)
                with self._lock:
                    self._ultimo = frame
        finally:
            cap.release()
            self._cap = None

    def parar_camara(self) -> None:
        """Suelta la camara y espera al hilo.

        Se espera de verdad (`join`): si la deteccion arranca mientras este hilo
        sigue dentro de `read()`, la camara continua ocupada y el otro proceso
        no puede abrirla.
        """
        self._parar.set()
        if self._hilo is not None:
            self._hilo.join(timeout=2.0)
            self._hilo = None
        with self._lock:
            self._ultimo = None

    # --- Fuente 2: los frames de la deteccion ------------------------------ #

    def escuchar(self, receptor) -> None:
        """Pasa a enseñar lo que publica el proceso de deteccion."""
        self._receptor = receptor
        self._mostrar_aviso(self._txt("vista_esperando"), "vista_esperando")
        self._programar()

    def dejar_de_escuchar(self) -> None:
        self._receptor = None

    # --- Bucle de refresco -------------------------------------------------- #

    def pausar(self) -> None:
        """Deja de pintar (ventana minimizada) sin soltar la camara.

        No se cierra la camara a proposito: abrirla otra vez cuesta segundos
        (hasta 20 con el backend compartido de Windows), asi que se paga el
        hilo lector, que es barato, y se ahorra lo caro, que es redimensionar y
        convertir 30 imagenes por segundo para una ventana que no se ve.
        """
        self._pausada = True
        if self._tarea is not None:
            try:
                self.lienzo.after_cancel(self._tarea)
            except tk.TclError:
                pass
            self._tarea = None

    def reanudar(self) -> None:
        self._pausada = False
        if self._receptor is not None or self._hilo is not None:
            self._programar()

    def _programar(self) -> None:
        if self._tarea is None and not self._pausada:
            self._tarea = self.lienzo.after(PERIODO_MS, self._tick)

    def _tick(self) -> None:
        self._tarea = None
        frame = None
        if self._receptor is not None:
            frame = self._receptor.leer()
        else:
            with self._lock:
                frame = self._ultimo
            if frame is False:              # la camara no abrio
                self._mostrar_aviso(self._txt("vista_sin_camara"),
                                    "vista_sin_camara")
                return                      # sin reprogramar: no hay nada que ver
        if frame is not None:
            try:
                self._pintar(frame)
            except tk.TclError:
                return                      # ventana cerrandose
        if self._receptor is not None or self._hilo is not None:
            self._programar()

    # --- Cierre ------------------------------------------------------------- #

    def parar(self) -> None:
        """Deja el panel quieto y en negro, sin camara ni puente."""
        self.parar_camara()
        self.dejar_de_escuchar()
        if self._tarea is not None:
            try:
                self.lienzo.after_cancel(self._tarea)
            except tk.TclError:
                pass
            self._tarea = None
        self.marcar(False)
        self.info.configure(text="")
        self._mostrar_aviso(self._txt("vista_parada"))
