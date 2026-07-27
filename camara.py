"""
Deteccion, seleccion y apertura de la webcam.

Dos objetivos:

1. COMPARTIR la camara con otras apps (Zoom, Teams, OBS...). En Windows lo
   decide el backend de captura:
     - Media Foundation (CAP_MSMF) pasa por el *Frame Server* de Windows, que
       permite que VARIAS aplicaciones lean la misma camara a la vez
       (Windows 10 1809+). Es lo que hace posible compartirla.
     - DirectShow (CAP_DSHOW) abre mas rapido pero BLOQUEA la camara en
       exclusiva: mientras este abierta, otra app no puede usarla.
   Con `compartir=True` se prueba MSMF primero. Aun asi, si otra app ya tiene la
   camara en exclusiva (apps viejas de DirectShow), no habra forma de compartir:
   es una limitacion del sistema/driver, no del programa.

2. ELEGIR el dispositivo: detecta las camaras conectadas y, si hay mas de una,
   abre un pequeno menu con una miniatura de cada una para que escojas. La
   eleccion se puede recordar en un JSON junto al programa.

Los nombres reales de los dispositivos aparecen si esta instalado `pygrabber`
(pip install pygrabber); si no, se muestran como "Camara 0", "Camara 1"...
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path

import cv2

# Backends por orden de preferencia segun se quiera compartir o no.
BACKEND_COMPARTIDO = getattr(cv2, "CAP_MSMF", cv2.CAP_ANY)   # Frame Server (comparte)
BACKEND_EXCLUSIVO = getattr(cv2, "CAP_DSHOW", cv2.CAP_ANY)   # DirectShow (rapido)


def backends(compartir: bool) -> list[int]:
    """Orden de backends a probar. El primero que funcione es el que se usa."""
    if compartir:
        return [BACKEND_COMPARTIDO, BACKEND_EXCLUSIVO]
    return [BACKEND_EXCLUSIVO, BACKEND_COMPARTIDO]


@dataclass
class Camara:
    """Una camara detectada, con su miniatura para el menu."""
    indice: int
    ancho: int
    alto: int
    backend: int
    nombre: str
    thumb_png64: str | None = None     # miniatura PNG en base64 (para tkinter)


# --------------------------------------------------------------------------- #
# Apertura y deteccion
# --------------------------------------------------------------------------- #

def _preparar(cap: cv2.VideoCapture, ancho: int, alto: int) -> None:
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, ancho)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, alto)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # menos latencia: no acumular frames


def _abrir_backend(indice: int, backend: int,
                   ancho: int | None, alto: int | None):
    """Abre `indice` con un backend concreto y devuelve (cap, primer_frame).

    Con `ancho=None` NO se fija la resolucion: es el modo "sondeo", mucho mas
    rapido (fijar la resolucion obliga a la camara a renegociar, sobre todo en
    MSMF). Se lee un frame porque `isOpened()` a veces miente. Devuelve None si
    la camara no existe o no da imagen.
    """
    cap = cv2.VideoCapture(indice, backend)
    if not cap.isOpened():
        cap.release()
        return None
    if ancho:
        _preparar(cap, ancho, alto)
    ok, frame = cap.read()
    if not ok or frame is None:
        cap.release()
        return None
    return cap, frame


def abrir(indice: int, ancho: int, alto: int,
          orden_backends: list[int]) -> tuple[cv2.VideoCapture | None, int | None]:
    """Abre la camara `indice` con el primer backend que entregue imagen."""
    for backend in orden_backends:
        r = _abrir_backend(indice, backend, ancho, alto)
        if r is not None:
            return r[0], backend
    return None, None


def _nombres_dispositivos() -> list[str]:
    """Nombres reales de las camaras via pygrabber, si esta disponible.

    El orden coincide con los indices de DirectShow. Puede no cuadrar al 100 %
    con los de MSMF, por eso el menu se apoya sobre todo en la miniatura.
    """
    try:
        from pygrabber.dshow_graph import FilterGraph
        return list(FilterGraph().get_input_devices())
    except Exception:            # noqa: BLE001  (pygrabber ausente o error COM)
        return []


def miniatura_png64(frame, ancho_dest: int = 240) -> str | None:
    """Reduce un frame BGR y lo devuelve como PNG en base64 (para tkinter).

    Se voltea en horizontal para que se vea en espejo, como en la app.
    """
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    alto, ancho = frame.shape[:2]
    escala = ancho_dest / ancho
    reducido = cv2.resize(frame, (ancho_dest, max(1, int(alto * escala))),
                          interpolation=cv2.INTER_AREA)
    reducido = cv2.flip(reducido, 1)
    ok, buf = cv2.imencode(".png", reducido)
    if not ok:
        return None
    return base64.b64encode(buf.tobytes()).decode("ascii")


def _detectar(max_indices: int, backend: int, nombres: list[str],
              backend_uso: int) -> list[Camara]:
    """Sondea los indices 0..max_indices-1 con un backend y arma las Camara.

    El sondeo no fija resolucion y lee un solo frame, que se reutiliza como
    miniatura. La camara guarda `backend_uso` (el que usara el capture real),
    no el del sondeo, para que la etiqueta del menu diga la verdad.
    """
    encontradas: list[Camara] = []
    for i in range(max_indices):
        r = _abrir_backend(i, backend, None, None)   # sondeo rapido
        if r is None:
            continue
        cap, frame = r
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        nombre = nombres[i] if i < len(nombres) else f"Camara {i}"
        encontradas.append(Camara(
            indice=i, ancho=w, alto=h, backend=backend_uso, nombre=nombre,
            thumb_png64=miniatura_png64(frame)))
    return encontradas


def listar(ancho: int, alto: int, orden_backends: list[int],
           max_indices: int) -> list[Camara]:
    """Detecta las camaras conectadas, rapido, con una miniatura de cada una.

    Primero sondea con DirectShow, que abre en milisegundos y falla al instante
    en indices vacios (MSMF puede tardar segundos por indice). Solo si asi no
    aparece ninguna se reintenta con el backend preferido, mas lento pero capaz
    de ver camaras que otra app tenga tomadas via el Frame Server.
    """
    nombres = _nombres_dispositivos()
    backend_uso = orden_backends[0]      # el que usara el capture real

    cams = _detectar(max_indices, BACKEND_EXCLUSIVO, nombres, backend_uso)
    if not cams and BACKEND_COMPARTIDO != BACKEND_EXCLUSIVO:
        cams = _detectar(max_indices, BACKEND_COMPARTIDO, nombres, backend_uso)
    return cams


def nombre_backend(backend: int) -> str:
    return {BACKEND_COMPARTIDO: "compartida (MSMF)",
            BACKEND_EXCLUSIVO: "exclusiva (DirectShow)"}.get(backend, "?")


# --------------------------------------------------------------------------- #
# Preferencia guardada
# --------------------------------------------------------------------------- #

def cargar_preferencia(ruta: Path) -> int | None:
    """Lee el indice de camara guardado, o None si no hay o el archivo es basura."""
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
        indice = datos.get("indice")
        return int(indice) if indice is not None else None
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def guardar_preferencia(ruta: Path, indice: int) -> None:
    try:
        Path(ruta).write_text(json.dumps({"indice": int(indice)}),
                              encoding="utf-8")
    except OSError:
        pass                     # no poder guardar la preferencia no es fatal


# --------------------------------------------------------------------------- #
# Decision: que camara usar (logica pura, sin cv2 ni tkinter)
# --------------------------------------------------------------------------- #

def elegir_indice(camaras: list[Camara], forzado: int | None,
                  guardado: int | None, menu_siempre: bool,
                  dialogo) -> tuple[int | None, bool]:
    """Decide que camara usar. Devuelve (indice, recordar).

    - `forzado` (INDICE_CAMARA fijado a mano) manda sobre todo.
    - una preferencia guardada que siga existiendo se respeta sin preguntar,
      salvo que `menu_siempre` obligue a mostrar el menu.
    - con una sola camara no se molesta al usuario.
    - en cualquier otro caso se llama a `dialogo(camaras, preseleccion)`, que
      devuelve (indice_elegido | None si cancela, recordar).
    """
    indices = {c.indice for c in camaras}

    if forzado is not None:
        return forzado, False

    if guardado in indices and not menu_siempre:
        return guardado, False

    if len(camaras) == 1 and not menu_siempre:
        return camaras[0].indice, False

    if not camaras:
        return None, False

    return dialogo(camaras, guardado)


# --------------------------------------------------------------------------- #
# Menu grafico (tkinter). Se mantiene fino a proposito y separado de la logica.
# --------------------------------------------------------------------------- #

def menu_grafico(camaras: list[Camara],
                 preseleccion: int | None) -> tuple[int | None, bool]:
    """Muestra un menu con la miniatura de cada camara. (indice|None, recordar)."""
    import tkinter as tk

    estado = {"indice": None, "recordar": False}
    raiz = tk.Tk()
    raiz.title("Elige tu camara")
    raiz.configure(bg="#1e1e1e")
    raiz.resizable(False, False)

    tk.Label(raiz, text="Camaras detectadas  ·  pulsa la que quieras usar",
             bg="#1e1e1e", fg="#e0e0e0", font=("Segoe UI", 11),
             pady=10).pack()

    fila = tk.Frame(raiz, bg="#1e1e1e")
    fila.pack(padx=14)
    imagenes = []                # hay que conservar las referencias o desaparecen

    def elegir(indice: int) -> None:
        # Leer el checkbox AQUI: tras destroy() el interprete de Tk desaparece.
        estado["indice"] = indice
        estado["recordar"] = bool(var_recordar.get())
        raiz.destroy()

    for cam in camaras:
        col = tk.Frame(fila, bg="#2a2a2a", bd=2, relief="ridge")
        col.pack(side="left", padx=6, pady=6)

        if cam.thumb_png64:
            img = tk.PhotoImage(data=cam.thumb_png64)
            imagenes.append(img)
            tk.Button(col, image=img, bd=0, cursor="hand2",
                      command=lambda i=cam.indice: elegir(i)).pack()
        else:
            tk.Button(col, text="(sin imagen)", width=28, height=8, bd=0,
                      command=lambda i=cam.indice: elegir(i)).pack()

        etiqueta = f"{cam.nombre}\n{cam.ancho}x{cam.alto} · {nombre_backend(cam.backend)}"
        borde = "#4c8cff" if cam.indice == preseleccion else "#2a2a2a"
        col.configure(highlightbackground=borde, highlightthickness=2)
        tk.Label(col, text=etiqueta, bg="#2a2a2a", fg="#cfcfcf",
                 font=("Segoe UI", 9), justify="center", pady=4).pack()

    var_recordar = tk.BooleanVar(value=preseleccion is not None)
    pie = tk.Frame(raiz, bg="#1e1e1e")
    pie.pack(pady=10)
    tk.Checkbutton(pie, text="Recordar mi eleccion", variable=var_recordar,
                   bg="#1e1e1e", fg="#e0e0e0", selectcolor="#1e1e1e",
                   activebackground="#1e1e1e", activeforeground="#e0e0e0").pack(
        side="left", padx=8)
    tk.Button(pie, text="Cancelar", command=raiz.destroy).pack(side="left", padx=8)

    raiz.update_idletasks()
    ancho = raiz.winfo_width()
    x = (raiz.winfo_screenwidth() - ancho) // 2
    raiz.geometry(f"+{x}+120")
    raiz.attributes("-topmost", True)
    raiz.mainloop()

    return estado["indice"], estado["recordar"]
