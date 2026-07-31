"""
Textos de la interfaz en varios idiomas.

Cada texto tiene una CLAVE estable; el codigo nunca escribe texto suelto, pide
la clave. Anadir un idioma es anadir un diccionario aqui: si le falta alguna
clave, se usa el espanol como respaldo en vez de romper la ventana.
"""

from __future__ import annotations

IDIOMAS = [("es", "Espanol"), ("en", "English")]
POR_DEFECTO = "es"

TEXTOS: dict[str, dict[str, str]] = {
    "es": {
        # --- Ventana principal ---
        "titulo": "Gestos · Control por camara",
        "app_titulo": "Control por gestos",
        "app_sub": "mueve el cursor con la mano",
        "sec_gestos": "GESTOS  ·  ELIGE QUE HACE CADA MANO",
        "sec_puntero": "PUNTERO",
        "sec_camara": "CAMARA",
        "sec_ayuda": "MIENTRAS DETECTA",
        "velocidad": "Velocidad",
        "velocidad_pista": "lento y preciso ←→ rapido",
        "aceleracion": "Aceleracion",
        "aceleracion_pista": "empuje extra en gestos amplios",
        "compartir_camara": "Compartir con otras apps (Zoom, Teams…)",
        "preguntar_camara": "Preguntar que camara usar al arrancar",
        "ayuda_deteccion": ("La ventana de camara no muestra texto.\n"
                            "Salir de la deteccion:  tecla  Q  o cerrar la ventana.\n"
                            "El gesto de on/off pausa el control sin cerrar nada."),
        "pista_gestos": ("Despliega para elegir raton o un atajo ya hecho.   "
                         "⌨ graba la combinacion\nde teclas que quieras "
                         "(incluida la tecla Windows).   ✕ deja el gesto sin "
                         "asignar."),
        "iniciar": "▶  Iniciar",
        "detener": "■  Detener",
        "guardar": "Guardar",
        "restablecer": "Restablecer",
        "ajustes": "⚙  Ajustes",
        "tema_claro": "☀  Claro",
        "tema_oscuro": "🌙  Oscuro",
        # --- Estados ---
        "estado_detenido": "Detenido",
        "estado_marcha": "En marcha · ponte frente a la camara",
        "estado_cerrado": "La deteccion se cerro",
        "estado_guardado": "Configuracion guardada",
        "estado_fabrica": "Valores de fabrica (sin guardar)",
        "estado_pulsa": "Pulsa las teclas…",
        "estado_cancelado": "Grabacion cancelada",
        "estado_sin_teclado": "No se pudo capturar el teclado en este equipo",
        "estado_sin_asignar": "{gesto} sin asignar",
        # --- Ajustes ---
        "ajustes_titulo": "Ajustes",
        "aj_general": "General",
        "aj_idioma": "Idioma",
        "aj_tema": "Tema",
        "aj_inicio": "Iniciar con Windows",
        "aj_inicio_pista": "La aplicacion se abrira sola al encender el equipo",
        "aj_minimizado": "Arrancar minimizado en la bandeja",
        "aj_autodeteccion": "Empezar a detectar al abrir",
        "aj_confirmar": "Preguntar antes de cerrar",
        "aj_deteccion": "Deteccion",
        "aj_espejo": "Ver la camara en espejo",
        "aj_estela": "Dibujar la estela del dedo",
        "aj_ventana": "Mostrar la ventana de la camara",
        "aj_resolucion": "Resolucion de captura",
        "aj_tiempos": "Tiempos",
        "aj_espera_atajo": "Mantener para lanzar un atajo (s)",
        "aj_espera_control": "Mantener para activar/desactivar (s)",
        "aj_avisos": "Avisos",
        "aj_sonido": "Sonido al hacer clic o lanzar un atajo",
        "aj_ayuda": "Ayuda",
        "aj_github": "🌐  Abrir el proyecto en GitHub",
        "aj_manual": "📖  Ver la guia de gestos",
        "aj_carpeta": "📁  Abrir la carpeta de configuracion",
        "aj_version": "Version {v}",
        "cerrar": "Cerrar",
        "aceptar": "Aceptar",
        "cancelar": "Cancelar",
        "confirmar_salir": "¿Cerrar la aplicacion?",
        # --- Instalador ---
        "inst_titulo": "Instalar Control por gestos",
        "inst_bienvenida": "Bienvenido",
        "inst_intro": ("Este asistente instalara Control por gestos en tu "
                       "equipo.\nElige donde quieres instalarlo y pulsa "
                       "Instalar."),
        "inst_carpeta": "Carpeta de instalacion",
        "inst_examinar": "Examinar…",
        "inst_idioma": "Idioma de la aplicacion",
        "inst_acceso": "Crear acceso directo en el Escritorio",
        "inst_menu": "Anadir al menu Inicio",
        "inst_autoarranque": "Iniciar con Windows",
        "inst_abrir": "Abrir la aplicacion al terminar",
        "inst_instalar": "Instalar",
        "inst_instalando": "Instalando…",
        "inst_listo": "Instalacion completada",
        "inst_error": "No se pudo instalar: {e}",
        "inst_espacio": "Se necesitan unos {mb} MB",
    },
    "en": {
        "titulo": "Gestures · Camera control",
        "app_titulo": "Gesture control",
        "app_sub": "move the cursor with your hand",
        "sec_gestos": "GESTURES  ·  CHOOSE WHAT EACH HAND DOES",
        "sec_puntero": "POINTER",
        "sec_camara": "CAMERA",
        "sec_ayuda": "WHILE DETECTING",
        "velocidad": "Speed",
        "velocidad_pista": "slow and precise ←→ fast",
        "aceleracion": "Acceleration",
        "aceleracion_pista": "extra push on wide gestures",
        "compartir_camara": "Share with other apps (Zoom, Teams…)",
        "preguntar_camara": "Ask which camera to use on startup",
        "ayuda_deteccion": ("The camera window shows no text.\n"
                            "Quit detection:  press  Q  or close the window.\n"
                            "The on/off gesture pauses control without closing."),
        "pista_gestos": ("Open the list to pick a mouse action or a ready-made "
                         "shortcut.   ⌨ records any\nkey combination (the "
                         "Windows key included).   ✕ clears the gesture."),
        "iniciar": "▶  Start",
        "detener": "■  Stop",
        "guardar": "Save",
        "restablecer": "Reset",
        "ajustes": "⚙  Settings",
        "tema_claro": "☀  Light",
        "tema_oscuro": "🌙  Dark",
        "estado_detenido": "Stopped",
        "estado_marcha": "Running · stand in front of the camera",
        "estado_cerrado": "Detection closed",
        "estado_guardado": "Settings saved",
        "estado_fabrica": "Factory defaults (not saved)",
        "estado_pulsa": "Press the keys…",
        "estado_cancelado": "Recording cancelled",
        "estado_sin_teclado": "Could not capture the keyboard on this machine",
        "estado_sin_asignar": "{gesto} unassigned",
        "ajustes_titulo": "Settings",
        "aj_general": "General",
        "aj_idioma": "Language",
        "aj_tema": "Theme",
        "aj_inicio": "Start with Windows",
        "aj_inicio_pista": "The app will open by itself when you turn the PC on",
        "aj_minimizado": "Start minimised to the tray",
        "aj_autodeteccion": "Start detecting on launch",
        "aj_confirmar": "Ask before closing",
        "aj_deteccion": "Detection",
        "aj_espejo": "Mirror the camera view",
        "aj_estela": "Draw the finger trail",
        "aj_ventana": "Show the camera window",
        "aj_resolucion": "Capture resolution",
        "aj_tiempos": "Timings",
        "aj_espera_atajo": "Hold to fire a shortcut (s)",
        "aj_espera_control": "Hold to enable/disable (s)",
        "aj_avisos": "Feedback",
        "aj_sonido": "Sound on click or shortcut",
        "aj_ayuda": "Help",
        "aj_github": "🌐  Open the project on GitHub",
        "aj_manual": "📖  See the gesture guide",
        "aj_carpeta": "📁  Open the settings folder",
        "aj_version": "Version {v}",
        "cerrar": "Close",
        "aceptar": "OK",
        "cancelar": "Cancel",
        "confirmar_salir": "Close the application?",
        "inst_titulo": "Install Gesture Control",
        "inst_bienvenida": "Welcome",
        "inst_intro": ("This wizard will install Gesture Control on your "
                       "computer.\nChoose where to install it and press "
                       "Install."),
        "inst_carpeta": "Installation folder",
        "inst_examinar": "Browse…",
        "inst_idioma": "Application language",
        "inst_acceso": "Create a Desktop shortcut",
        "inst_menu": "Add to the Start menu",
        "inst_autoarranque": "Start with Windows",
        "inst_abrir": "Open the app when finished",
        "inst_instalar": "Install",
        "inst_instalando": "Installing…",
        "inst_listo": "Installation complete",
        "inst_error": "Could not install: {e}",
        "inst_espacio": "About {mb} MB needed",
    },
}

URL_GITHUB = "https://github.com/swaazzyy/automatization-signs"
VERSION = "2.0"


class Textos:
    """Traductor: `t("clave")` devuelve el texto en el idioma elegido."""

    def __init__(self, idioma: str = POR_DEFECTO) -> None:
        self.cambiar(idioma)

    def cambiar(self, idioma: str) -> None:
        self.idioma = idioma if idioma in TEXTOS else POR_DEFECTO
        self._d = TEXTOS[self.idioma]
        self._respaldo = TEXTOS[POR_DEFECTO]

    def __call__(self, clave: str, **fmt) -> str:
        # Si a un idioma le falta una clave se usa el espanol: nunca se muestra
        # el identificador crudo ni salta una excepcion en mitad de la ventana.
        texto = self._d.get(clave) or self._respaldo.get(clave) or clave
        return texto.format(**fmt) if fmt else texto
