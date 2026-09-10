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
# Solo IDENTIFICADORES: el texto visible vive en idiomas.py, para que se pueda
# traducir. El orden es el que se muestra en el editor de gestos.
FORMAS = ["un_dedo", "dos_dedos", "tres_dedos", "pulgar", "mano_abierta",
          "puno", "pulgar_menique"]

# Acciones de raton y control. No son atajos: las gestiona la propia app.
ACCIONES_BASE = ["mover", "clic_izq", "clic_der", "alternar", "nada"]

# Catalogo de ATAJOS DE WINDOWS: id -> teclas. El texto visible esta en
# idiomas.py (clave "accion_<id>") y el emoji en EMOJI_ACCION, porque ni las
# teclas ni el emoji dependen del idioma.
ATAJOS = {
    # --- Ventanas ---
    "maximizar":    ("win", "arriba"),
    "minimizar":    ("win", "abajo"),
    "acoplar_izq":  ("win", "izquierda"),
    "acoplar_der":  ("win", "derecha"),
    "cerrar_app":   ("alt", "f4"),
    "pantalla_completa": ("f11",),
    # --- Cambiar de aplicacion ---
    "cambiar_app":  ("alt", "tab"),
    "vista_tareas": ("win", "tab"),
    "escritorio":   ("win", "d"),
    "escritorio_der": ("win", "ctrl", "derecha"),
    "escritorio_izq": ("win", "ctrl", "izquierda"),
    # --- Sistema ---
    "explorador":   ("win", "e"),
    "ajustes":      ("win", "i"),
    "buscar":       ("win", "s"),
    "bloquear":     ("win", "l"),
    "captura":      ("win", "shift", "s"),
    "emoji":        ("win", "."),
    # --- Edicion ---
    "copiar":       ("ctrl", "c"),
    "pegar":        ("ctrl", "v"),
    "deshacer":     ("ctrl", "z"),
    "rehacer":      ("ctrl", "y"),
    "seleccionar":  ("ctrl", "a"),
    "guardar_doc":  ("ctrl", "s"),
    # --- Multimedia ---
    "vol_subir":    ("vol_subir",),
    "vol_bajar":    ("vol_bajar",),
    "silencio":     ("silencio",),
    "play":         ("play",),
    "siguiente":    ("siguiente",),
    "anterior":     ("anterior",),
    # --- Navegador ---
    "pestana_nueva": ("ctrl", "t"),
    "cerrar_pestana": ("ctrl", "w"),
    "recargar":     ("f5",),
}

# Emoji de cada accion: no depende del idioma, asi que vive aqui.
EMOJI_ACCION = {
    "mover": "🖱️", "clic_izq": "👆", "clic_der": "👉", "alternar": "⏯️",
    "nada": "🚫",
    "maximizar": "🔼", "minimizar": "🔽", "acoplar_izq": "◀️",
    "acoplar_der": "▶️", "cerrar_app": "❌", "pantalla_completa": "🖥️",
    "cambiar_app": "🔄", "vista_tareas": "🗂️", "escritorio": "🖥️",
    "escritorio_der": "➡️", "escritorio_izq": "⬅️",
    "explorador": "📁", "ajustes": "⚙️", "buscar": "🔎", "bloquear": "🔒",
    "captura": "📸", "emoji": "😀",
    "copiar": "📋", "pegar": "📥", "deshacer": "↩️", "rehacer": "↪️",
    "seleccionar": "🔲", "guardar_doc": "💾",
    "vol_subir": "🔊", "vol_bajar": "🔉", "silencio": "🔇", "play": "⏯️",
    "siguiente": "⏭️", "anterior": "⏮️",
    "pestana_nueva": "➕", "cerrar_pestana": "✖️", "recargar": "🔃",
}

# Agrupacion para el menu de la GUI: con 30+ opciones, una lista plana es
# inmanejable. El orden de los ids dentro de cada grupo es el de ATAJOS.
# Grupos del menu. El titulo es una CLAVE de idiomas, no texto suelto.
GRUPOS = [
    ("grupo_raton", list(ACCIONES_BASE)),
    ("grupo_ventanas", ["maximizar", "minimizar", "acoplar_izq", "acoplar_der",
                        "cerrar_app", "pantalla_completa"]),
    ("grupo_cambiar", ["cambiar_app", "vista_tareas", "escritorio",
                       "escritorio_izq", "escritorio_der"]),
    ("grupo_sistema", ["explorador", "ajustes", "buscar", "bloquear", "captura",
                       "emoji"]),
    ("grupo_edicion", ["copiar", "pegar", "deshacer", "rehacer", "seleccionar",
                       "guardar_doc"]),
    ("grupo_multimedia", ["vol_subir", "vol_bajar", "silencio", "play",
                          "siguiente", "anterior"]),
    ("grupo_navegador", ["pestana_nueva", "cerrar_pestana", "recargar"]),
]

IDS_FORMAS = list(FORMAS)
IDS_ACCIONES = ACCIONES_BASE + list(ATAJOS)


# Resoluciones de captura que ofrece el selector de ajustes
RESOLUCIONES = ["640x480", "960x540", "1280x720", "1920x1080"]

PREFIJO_PROPIO = "propio:"


def id_propio(teclas) -> str:
    """Id estable de un atajo grabado: su propia combinacion de teclas.

    Al derivarlo de las teclas, grabar dos veces lo mismo no crea duplicados.
    """
    return PREFIJO_PROPIO + "+".join(teclas)


# `t` (el traductor) y `cfg` son obligatorios: no hay ni una llamada en la app
# que los omita. Cuando tenian valor por defecto, cada funcion arrastraba una
# rama "sin traductor" que devolvia el identificador crudo y que nadie ejecutaba
# jamas; lo unico que hacia era esconder un error si algun dia se llamaba mal.
def etiqueta_forma(fid: str, t) -> str:
    """Nombre visible de una forma de la mano, en el idioma activo."""
    return t(f"forma_{fid}")


def etiqueta_accion(aid: str, t, cfg: dict) -> str:
    """Nombre visible de una accion: emoji + texto traducido.

    Los atajos que graba el usuario llevan el nombre que el mismo les puso (la
    propia combinacion de teclas), asi que no se traducen.
    """
    propio = cfg.get("atajos_propios", {}).get(aid)
    if propio:
        return propio["nombre"]
    return f"{EMOJI_ACCION.get(aid, '')} {t(f'accion_{aid}')}".strip()


def acciones(cfg: dict, t) -> list[tuple[str, str]]:
    """Acciones disponibles: las de raton, el catalogo y los atajos del usuario."""
    lista = [(aid, etiqueta_accion(aid, t, cfg)) for aid in IDS_ACCIONES]
    for aid, datos in cfg.get("atajos_propios", {}).items():
        lista.append((aid, datos["nombre"]))
    return lista


def grupos(cfg: dict, t) -> list[tuple[str, list[str]]]:
    """Como `GRUPOS` pero con los titulos traducidos y los atajos propios."""
    lista = [(t(clave), ids) for clave, ids in GRUPOS]
    propios = list(cfg.get("atajos_propios", {}))
    if propios:
        lista.append((t("grupo_propios"), propios))
    return lista


def teclas_de(accion: str, cfg: dict | None = None) -> tuple[str, ...] | None:
    """Combinacion de teclas de una accion, o None si no es un atajo.

    `ATAJOS[accion]` YA es la tupla de teclas: devolverla entera. (Antes el
    valor era `(etiqueta, teclas)` y aqui se hacia `entrada[1]`; al mover la
    etiqueta a idiomas.py eso paso a devolver una sola tecla como cadena, y
    como una cadena es iterable la app acababa tecleando sus letras una a una
    en vez de ejecutar el atajo.)
    """
    entrada = ATAJOS.get(accion)
    if entrada is not None:
        return tuple(entrada)
    propio = (cfg or {}).get("atajos_propios", {}).get(accion)
    return tuple(propio["teclas"]) if propio else None

# --------------------------------------------------------------------------- #
# Valores por defecto (reproducen el comportamiento actual)
# --------------------------------------------------------------------------- #

DEFECTO = {
    "tema": "oscuro",                       # "oscuro" | "claro"
    "idioma": "es",                         # ver idiomas.IDIOMAS
    # --- Comportamiento de la aplicacion ---
    "app": {
        "autoarranque": False,              # abrirse al iniciar Windows
        "arrancar_minimizado": False,
        "detectar_al_abrir": False,         # empezar a detectar sin pulsar nada
        "confirmar_salida": False,
        "sonido": True,                     # pitido al hacer clic / lanzar atajo
    },
    # --- Deteccion ---
    "deteccion": {
        "espejo": True,                     # ver la camara como un espejo
        "estela": True,                     # dibujar el rastro del dedo
        "mostrar_ventana": True,            # ver la ventana de la camara
        "hud": True,                        # panel de estado sobre la camara
        "vista_previa": True,               # ver la camara en la ventana principal
        "resolucion": "960x540",
        "espera_atajo": 0.35,               # s manteniendo para lanzar un atajo
        "espera_control": 1.2,              # s para activar/desactivar
    },
    "gestos": {
        "un_dedo": "mover",              # el indice SIEMPRE senala: no se cambia
        "dos_dedos": "clic_izq",
        "tres_dedos": "cambiar_app",     # como un Alt+Tab
        "pulgar": "clic_der",
        "mano_abierta": "maximizar",     # pantalla completa
        "puno": "minimizar",
        "pulgar_menique": "alternar",
    },
    "sensibilidad": {
        "ganancia": 2.0,                    # ver tabla en el README
        "aceleracion": 1.4,
    },
    "camara": {
        "indice": None,                     # None = detectar / preguntar
        "compartir": True,                  # MSMF (compartir con otras apps)
    },
    # Atajos grabados por el usuario: id -> {"nombre": str, "teclas": [str,...]}
    # Sus claves son dinamicas, asi que se copian tal cual (ver _fusionar).
    "atajos_propios": {},
}

# Claves cuyo contenido NO se fusiona campo a campo, porque el usuario decide
# que hay dentro. Sin esto, _fusionar las vaciaria en cada carga.
CLAVES_LIBRES = ("atajos_propios",)

RUTA_DEFECTO_NOMBRE = "config.json"


def _fusionar(base: dict, encima: dict) -> dict:
    """Copia profunda de `base` con lo que traiga `encima` puesto por encima.

    Solo se aceptan claves que existan en `base`, asi que un config viejo o
    manipulado nunca introduce campos raros ni rompe la app.
    """
    resultado = {}
    for clave, valor_base in base.items():
        if clave in CLAVES_LIBRES:
            propio = (encima or {}).get(clave)
            resultado[clave] = dict(propio) if isinstance(propio, dict) else {}
        elif isinstance(valor_base, dict):
            resultado[clave] = _fusionar(valor_base, (encima or {}).get(clave, {}))
        else:
            resultado[clave] = (encima or {}).get(clave, valor_base)
    return resultado


def _validar(cfg: dict) -> dict:
    """Corrige valores imposibles para que la deteccion nunca reciba basura."""
    if cfg["tema"] not in ("oscuro", "claro"):
        cfg["tema"] = DEFECTO["tema"]

    import idiomas                          # aqui: evita ciclos al importar
    if cfg["idioma"] not in dict(idiomas.IDIOMAS):
        cfg["idioma"] = DEFECTO["idioma"]

    for clave in ("autoarranque", "arrancar_minimizado", "detectar_al_abrir",
                  "confirmar_salida", "sonido"):
        cfg["app"][clave] = bool(cfg["app"].get(clave, DEFECTO["app"][clave]))

    d = cfg["deteccion"]
    for clave in ("espejo", "estela", "mostrar_ventana", "hud", "vista_previa"):
        d[clave] = bool(d.get(clave, DEFECTO["deteccion"][clave]))
    if d.get("resolucion") not in RESOLUCIONES:
        d["resolucion"] = DEFECTO["deteccion"]["resolucion"]
    for clave, minimo, maximo in (("espera_atajo", 0.1, 2.0),
                                  ("espera_control", 0.3, 5.0)):
        try:
            d[clave] = min(maximo, max(minimo, float(d[clave])))
        except (TypeError, ValueError, KeyError):
            d[clave] = DEFECTO["deteccion"][clave]

    # Atajos propios: se descarta lo que no tenga forma de atajo enviable, para
    # que un archivo editado a mano no deje la deteccion con teclas invalidas.
    from control_windows import VK          # import aqui: evita ciclo al cargar
    limpios = {}
    for aid, datos in (cfg.get("atajos_propios") or {}).items():
        if not isinstance(datos, dict):
            continue
        teclas = datos.get("teclas")
        nombre = datos.get("nombre")
        if (isinstance(teclas, (list, tuple)) and teclas
                and all(isinstance(t, str) and t in VK for t in teclas)
                and isinstance(nombre, str) and nombre.strip()):
            limpios[str(aid)] = {"nombre": nombre.strip(),
                                 "teclas": list(teclas)}
    cfg["atajos_propios"] = limpios

    validas = set(IDS_ACCIONES) | set(limpios)
    for forma in IDS_FORMAS:
        if cfg["gestos"].get(forma) not in validas:
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
