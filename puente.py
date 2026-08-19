"""
Puente de frames entre el proceso de deteccion y la ventana principal.

La deteccion corre en OTRO proceso (para que un fallo suyo no se lleve por
delante la ventana, y para poder pararla de golpe), pero la vista previa se
dibuja en la ventana. Hay que pasar imagenes de 1 a 60 veces por segundo entre
los dos, asi que se usa memoria compartida: la alternativa era mandarlas por una
tuberia, y copiar y serializar 3 MB por frame se come el procesador que necesita
MediaPipe.

Solo interesa el ULTIMO frame. No hay cola ni buffer: el emisor sobreescribe
siempre el mismo hueco y el receptor lee lo que haya cuando le toca mirar. Si la
ventana va mas lenta que la camara, se salta frames y no pasa nada; con una cola
acabaria mostrando imagenes viejas y acumulando retraso.

Para no leer un frame a medio escribir se usa un contador de version (el patron
"seqlock", sin bloqueos ni esperas):

    - el emisor sube el contador a IMPAR, escribe, y lo sube a PAR;
    - el receptor lee el contador, copia, y vuelve a leerlo: si cambio o era
      impar, es que le pillo escribiendo y lo reintenta.

Asi ninguno de los dos espera nunca al otro, que es justo lo que no puede pasar
en el bucle de deteccion.
"""

from __future__ import annotations

import os
import struct

import numpy as np
from multiprocessing import shared_memory

# Cabecera: version, ancho, alto y canales, cuatro enteros de 32 bits.
CABECERA = 16
FORMATO = "<IIII"

# El hueco se reserva para el frame mas grande que ofrece la app (1080p). Son
# 6 MB de memoria virtual, y el sistema solo compromete de verdad las paginas
# que se tocan, asi que con una camara de 640x480 no cuesta lo mismo.
ANCHO_MAX, ALTO_MAX = 1920, 1080
TAMANO = CABECERA + ANCHO_MAX * ALTO_MAX * 3


def _nombre_nuevo() -> str:
    """Nombre unico para el bloque compartido de esta ejecucion."""
    return f"gestos_vista_{os.getpid()}_{os.urandom(3).hex()}"


class Receptor:
    """Crea el bloque y lee el ultimo frame. Vive en la ventana principal."""

    def __init__(self) -> None:
        self._shm = shared_memory.SharedMemory(create=True, size=TAMANO,
                                               name=_nombre_nuevo())
        self._shm.buf[:CABECERA] = b"\0" * CABECERA
        self.nombre = self._shm.name

    def leer(self):
        """Ultimo frame completo (BGR), o None si aun no hay ninguno.

        Devuelve SIEMPRE una copia: la vista apunta a memoria que el emisor
        puede reescribir en cualquier momento, y dibujarla directamente daria
        imagenes partidas por la mitad.
        """
        buf = self._shm.buf
        for _ in range(3):                 # 3 intentos: mas ya seria mala suerte
            version, ancho, alto, canales = struct.unpack_from(FORMATO, buf, 0)
            if version == 0 or version % 2:      # nada escrito, o escribiendo
                return None
            if not (0 < ancho <= ANCHO_MAX and 0 < alto <= ALTO_MAX
                    and canales == 3):
                return None
            vista = np.ndarray((alto, ancho, canales), np.uint8,
                               buffer=buf, offset=CABECERA)
            copia = vista.copy()
            del vista                      # sin esto el buffer queda exportado
            if struct.unpack_from("<I", buf, 0)[0] == version:
                return copia
        return None

    def cerrar(self) -> None:
        try:
            self._shm.close()
            self._shm.unlink()             # en Windows no hace nada, pero toca
        except (BufferError, FileNotFoundError, OSError):
            pass                           # cerrar nunca debe romper la salida


class Emisor:
    """Escribe el ultimo frame. Vive en el proceso de deteccion."""

    def __init__(self, nombre: str) -> None:
        self._shm = shared_memory.SharedMemory(name=nombre)
        self._version = 0

    def enviar(self, frame) -> bool:
        """Publica el frame. False si no cabe (camara mas grande de lo previsto)."""
        alto, ancho = frame.shape[:2]
        if ancho > ANCHO_MAX or alto > ALTO_MAX or frame.shape[2] != 3:
            return False
        buf = self._shm.buf
        self._version += 1                 # impar: no mires, estoy escribiendo
        struct.pack_into(FORMATO, buf, 0, self._version, ancho, alto, 3)
        destino = np.ndarray((alto, ancho, 3), np.uint8,
                             buffer=buf, offset=CABECERA)
        destino[:] = frame
        del destino
        self._version += 1                 # par: ya puedes leerlo
        struct.pack_into("<I", buf, 0, self._version)
        return True

    def cerrar(self) -> None:
        try:
            self._shm.close()
        except (BufferError, OSError):
            pass
