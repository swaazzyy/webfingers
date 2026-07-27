"""
Configuracion compartida entre el launcher (GUI) y la deteccion.

Se guarda en `config.json` junto al programa. El launcher la edita; la deteccion
la lee al arrancar. Todo es texto plano (JSON) para que se pueda revisar y editar
a mano si hace falta.

Diseno por "formas" y "acciones":
- una FORMA es como pones la mano (1 dedo, 2 dedos, puno...). La detecta la
  camara y no se puede cambiar.
- una ACCION es lo que hace (mover el cursor, clic izquierdo, zoom...).
- el usuario edita el MAPA forma -> accion. Asi puede, por ejemplo, poner el
  clic derecho en "3 dedos" en vez de en el pulgar.
"""

from __future__ import annotations

import json
from pathlib import Path

# --------------------------------------------------------------------------- #
# Vocabulario (ids estables + etiqueta para la GUI)
# --------------------------------------------------------------------------- #

# Formas de la mano. El orden es el que se muestra en el editor.
FORMAS = [
    ("un_dedo",        "1 dedo (indice)"),
    ("dos_dedos",      "2 dedos (indice + medio)"),
    ("tres_dedos",     "3 dedos (indice + medio + anular)"),
    ("pulgar",         "Pulgar arriba"),
    ("mano_abierta",   "Mano abierta (5 dedos)"),
    ("puno",           "Puno (0 dedos)"),
    ("pulgar_menique", "Pulgar + menique"),
]

# Acciones asignables. "nada" desactiva la forma.
ACCIONES = [
    ("mover",     "Mover el cursor"),
    ("clic_izq",  "Clic izquierdo / arrastrar"),
    ("clic_der",  "Clic derecho"),
    ("zoom_in",   "Acercar (lupa)"),
    ("zoom_out",  "Alejar (lupa)"),
    ("alternar",  "Activar/desactivar control"),
    ("nada",      "Nada"),
]

IDS_FORMAS = [f for f, _ in FORMAS]
IDS_ACCIONES = [a for a, _ in ACCIONES]
ETIQUETA_FORMA = dict(FORMAS)
ETIQUETA_ACCION = dict(ACCIONES)

# --------------------------------------------------------------------------- #
# Valores por defecto (reproducen el comportamiento actual)
# --------------------------------------------------------------------------- #

DEFECTO = {
    "tema": "oscuro",                       # "oscuro" | "claro"
    "gestos": {
        "un_dedo": "mover",
        "dos_dedos": "clic_izq",
        "tres_dedos": "nada",
        "pulgar": "clic_der",
        "mano_abierta": "zoom_in",
        "puno": "zoom_out",
        "pulgar_menique": "alternar",
    },
    "sensibilidad": {
        "ganancia": 2.0,                    # ver tabla en el README
        "aceleracion": 1.4,
    },
    "camara": {
        "indice": None,                     # None = detectar / preguntar
        "compartir": True,                  # MSMF (compartir con otras apps)
        "menu_siempre": False,
    },
}

RUTA_DEFECTO_NOMBRE = "config.json"


def _fusionar(base: dict, encima: dict) -> dict:
    """Copia profunda de `base` con lo que traiga `encima` puesto por encima.

    Solo se aceptan claves que existan en `base`, asi que un config viejo o
    manipulado nunca introduce campos raros ni rompe la app.
    """
    resultado = {}
    for clave, valor_base in base.items():
        if isinstance(valor_base, dict):
            resultado[clave] = _fusionar(valor_base, (encima or {}).get(clave, {}))
        else:
            resultado[clave] = (encima or {}).get(clave, valor_base)
    return resultado


def _validar(cfg: dict) -> dict:
    """Corrige valores imposibles para que la deteccion nunca reciba basura."""
    if cfg["tema"] not in ("oscuro", "claro"):
        cfg["tema"] = DEFECTO["tema"]

    for forma in IDS_FORMAS:
        if cfg["gestos"].get(forma) not in IDS_ACCIONES:
            cfg["gestos"][forma] = DEFECTO["gestos"][forma]

    s = cfg["sensibilidad"]
    try:
        s["ganancia"] = min(6.0, max(0.5, float(s["ganancia"])))
    except (TypeError, ValueError):
        s["ganancia"] = DEFECTO["sensibilidad"]["ganancia"]
    try:
        s["aceleracion"] = min(4.0, max(0.0, float(s["aceleracion"])))
    except (TypeError, ValueError):
        s["aceleracion"] = DEFECTO["sensibilidad"]["aceleracion"]

    ind = cfg["camara"]["indice"]
    if ind is not None:
        try:
            cfg["camara"]["indice"] = int(ind)
        except (TypeError, ValueError):
            cfg["camara"]["indice"] = None
    cfg["camara"]["compartir"] = bool(cfg["camara"]["compartir"])
    cfg["camara"]["menu_siempre"] = bool(cfg["camara"]["menu_siempre"])
    return cfg


def cargar(ruta: Path) -> dict:
    """Lee la configuracion, rellenando lo que falte con los valores por defecto.

    Nunca lanza: si el archivo no existe o esta corrupto, devuelve los defectos.
    """
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        datos = {}
    return _validar(_fusionar(DEFECTO, datos if isinstance(datos, dict) else {}))


def guardar(ruta: Path, cfg: dict) -> None:
    """Guarda la configuracion (validada) de forma legible."""
    limpio = _validar(_fusionar(DEFECTO, cfg))
    Path(ruta).write_text(json.dumps(limpio, indent=2, ensure_ascii=False),
                          encoding="utf-8")


def por_defecto() -> dict:
    """Copia nueva de la configuracion por defecto."""
    return _fusionar(DEFECTO, {})
