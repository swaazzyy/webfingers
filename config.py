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
    ("un_dedo",        "1 dedo  ·  indice"),
    ("dos_dedos",      "2 dedos  ·  + medio"),
    ("tres_dedos",     "3 dedos  ·  + anular"),
    ("pulgar",         "Pulgar arriba"),
    ("mano_abierta",   "Mano abierta  ·  5 dedos"),
    ("puno",           "Puno  ·  0 dedos"),
    ("pulgar_menique", "Pulgar + menique"),
]

# Acciones de raton y control. No son atajos: las gestiona la propia app.
ACCIONES_BASE = [
    ("mover",    "🖱️ Mover el cursor"),
    ("clic_izq", "👆 Clic izquierdo / arrastrar"),
    ("clic_der", "👉 Clic derecho"),
    ("alternar", "⏯️ Activar / desactivar"),
    ("nada",     "🚫 Nada"),
]

# Catalogo de ATAJOS DE WINDOWS: id -> (etiqueta con emoji, teclas).
# Anadir uno nuevo es anadir una linea aqui; ni la deteccion ni la GUI cambian.
ATAJOS = {
    # --- Ventanas ---
    "maximizar":    ("🔼 Maximizar ventana", ("win", "arriba")),
    "minimizar":    ("🔽 Minimizar ventana", ("win", "abajo")),
    "acoplar_izq":  ("◀️ Acoplar a la izquierda", ("win", "izquierda")),
    "acoplar_der":  ("▶️ Acoplar a la derecha", ("win", "derecha")),
    "cerrar_app":   ("❌ Cerrar ventana", ("alt", "f4")),
    "pantalla_completa": ("🖥️ Pantalla completa", ("f11",)),
    # --- Cambiar de aplicacion ---
    "cambiar_app":  ("🔄 Cambiar de aplicacion", ("alt", "tab")),
    "vista_tareas": ("🗂️ Vista de tareas", ("win", "tab")),
    "escritorio":   ("🖥️ Mostrar el escritorio", ("win", "d")),
    "escritorio_der": ("➡️ Escritorio siguiente", ("win", "ctrl", "derecha")),
    "escritorio_izq": ("⬅️ Escritorio anterior", ("win", "ctrl", "izquierda")),
    # --- Sistema ---
    "explorador":   ("📁 Abrir el Explorador", ("win", "e")),
    "ajustes":      ("⚙️ Abrir Configuracion", ("win", "i")),
    "buscar":       ("🔎 Buscar en Windows", ("win", "s")),
    "bloquear":     ("🔒 Bloquear el equipo", ("win", "l")),
    "captura":      ("📸 Recorte de pantalla", ("win", "shift", "s")),
    "emoji":        ("😀 Panel de emoji", ("win", ".")),
    # --- Edicion ---
    "copiar":       ("📋 Copiar", ("ctrl", "c")),
    "pegar":        ("📥 Pegar", ("ctrl", "v")),
    "deshacer":     ("↩️ Deshacer", ("ctrl", "z")),
    "rehacer":      ("↪️ Rehacer", ("ctrl", "y")),
    "seleccionar":  ("🔲 Seleccionar todo", ("ctrl", "a")),
    "guardar_doc":  ("💾 Guardar", ("ctrl", "s")),
    # --- Multimedia ---
    "vol_subir":    ("🔊 Subir volumen", ("vol_subir",)),
    "vol_bajar":    ("🔉 Bajar volumen", ("vol_bajar",)),
    "silencio":     ("🔇 Silenciar", ("silencio",)),
    "play":         ("⏯️ Reproducir / pausar", ("play",)),
    "siguiente":    ("⏭️ Pista siguiente", ("siguiente",)),
    "anterior":     ("⏮️ Pista anterior", ("anterior",)),
    # --- Navegador ---
    "pestana_nueva": ("➕ Pestana nueva", ("ctrl", "t")),
    "cerrar_pestana": ("✖️ Cerrar pestana", ("ctrl", "w")),
    "recargar":     ("🔃 Recargar", ("f5",)),
}

# Agrupacion para el menu de la GUI: con 30+ opciones, una lista plana es
# inmanejable. El orden de los ids dentro de cada grupo es el de ATAJOS.
GRUPOS = [
    ("Raton y control", [a for a, _ in ACCIONES_BASE]),
    ("Ventanas", ["maximizar", "minimizar", "acoplar_izq", "acoplar_der",
                  "cerrar_app", "pantalla_completa"]),
    ("Cambiar de aplicacion", ["cambiar_app", "vista_tareas", "escritorio",
                               "escritorio_izq", "escritorio_der"]),
    ("Sistema", ["explorador", "ajustes", "buscar", "bloquear", "captura",
                 "emoji"]),
    ("Edicion", ["copiar", "pegar", "deshacer", "rehacer", "seleccionar",
                 "guardar_doc"]),
    ("Multimedia", ["vol_subir", "vol_bajar", "silencio", "play", "siguiente",
                    "anterior"]),
    ("Navegador", ["pestana_nueva", "cerrar_pestana", "recargar"]),
]

# La lista que ve el usuario: primero lo de raton, luego todos los atajos.
ACCIONES = ACCIONES_BASE + [(aid, etiqueta) for aid, (etiqueta, _) in ATAJOS.items()]

IDS_FORMAS = [f for f, _ in FORMAS]
IDS_ACCIONES = [a for a, _ in ACCIONES]
ETIQUETA_FORMA = dict(FORMAS)
ETIQUETA_ACCION = dict(ACCIONES)


# Resoluciones de captura que ofrece el selector de ajustes
RESOLUCIONES = ["640x480", "960x540", "1280x720", "1920x1080"]

PREFIJO_PROPIO = "propio:"


def id_propio(teclas) -> str:
    """Id estable de un atajo grabado: su propia combinacion de teclas.

    Al derivarlo de las teclas, grabar dos veces lo mismo no crea duplicados.
    """
    return PREFIJO_PROPIO + "+".join(teclas)


def acciones(cfg: dict | None = None) -> list[tuple[str, str]]:
    """Acciones disponibles: las de raton, el catalogo y los atajos del usuario."""
    lista = list(ACCIONES)
    for aid, datos in (cfg or {}).get("atajos_propios", {}).items():
        lista.append((aid, datos["nombre"]))
    return lista


def grupos(cfg: dict | None = None) -> list[tuple[str, list[str]]]:
    """Como `GRUPOS`, anadiendo al final el grupo de atajos propios si los hay."""
    lista = list(GRUPOS)
    propios = list((cfg or {}).get("atajos_propios", {}))
    if propios:
        lista.append(("Mis atajos", propios))
    return lista


def teclas_de(accion: str, cfg: dict | None = None) -> tuple[str, ...] | None:
    """Combinacion de teclas de una accion, o None si no es un atajo."""
    entrada = ATAJOS.get(accion)
    if entrada:
        return entrada[1]
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
        "menu_siempre": False,
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
    for clave in ("espejo", "estela", "mostrar_ventana"):
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
