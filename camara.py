"""
Apertura de la webcam.

COMPARTIR la camara con otras apps (Zoom, Teams, OBS...) lo decide el backend:

  - Media Foundation (CAP_MSMF) pasa por el *Frame Server* de Windows, que
    permite que VARIAS aplicaciones lean la misma camara a la vez
    (Windows 10 1809+). Es lo que hace posible compartirla, pero abrir tarda
    mucho mas: medido en un equipo, 19 s frente a 4 s.
  - DirectShow (CAP_DSHOW) abre rapido pero BLOQUEA la camara en exclusiva.
  - En Linux/macOS no hay ninguno de los dos y se usa el backend por defecto
    (V4L2 / AVFoundation), donde compartir depende del driver.

Aun con MSMF, si otra app ya tiene la camara en exclusiva (apps viejas de
DirectShow) no habra forma de compartir: es una limitacion del sistema.

Que camara se usa lo decide `config.json` ("camara": {"indice": N}); con
`indice: null` se abre la primera que responda.
"""

from __future__ import annotations

import cv2

# Backends por orden de preferencia segun se quiera compartir o no. En sistemas
# donde no existen, `getattr` cae en CAP_ANY y la lista queda con el backend por
# defecto repetido, que es justo lo que se quiere: probar el unico que hay.
BACKEND_COMPARTIDO = getattr(cv2, "CAP_MSMF", cv2.CAP_ANY)   # Frame Server
BACKEND_EXCLUSIVO = getattr(cv2, "CAP_DSHOW", cv2.CAP_ANY)   # DirectShow


def backends(compartir: bool) -> list[int]:
    """Orden de backends a probar. El primero que funcione es el que se usa."""
    if compartir:
        return [BACKEND_COMPARTIDO, BACKEND_EXCLUSIVO]
    return [BACKEND_EXCLUSIVO, BACKEND_COMPARTIDO]


def _preparar(cap: cv2.VideoCapture, ancho: int, alto: int) -> None:
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, ancho)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, alto)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # menos latencia: no acumular frames


def abrir(indice: int, ancho: int, alto: int,
          orden_backends: list[int]) -> tuple[cv2.VideoCapture | None, int | None]:
    """Abre la camara `indice` con el primer backend que entregue imagen.

    Se lee un frame antes de darla por buena porque `isOpened()` a veces miente:
    devuelve True con camaras que no existen o que otra app tiene ocupadas.
    """
    for backend in orden_backends:
        cap = cv2.VideoCapture(indice, backend)
        if not cap.isOpened():
            cap.release()
            continue
        _preparar(cap, ancho, alto)
        ok, frame = cap.read()
        if ok and frame is not None:
            return cap, backend
        cap.release()
    return None, None


def nombre_backend(backend: int) -> str:
    return {BACKEND_COMPARTIDO: "compartida (MSMF)",
            BACKEND_EXCLUSIVO: "exclusiva (DirectShow)"}.get(backend, "por defecto")
