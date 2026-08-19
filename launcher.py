"""
Launcher grafico del detector de gestos.

Es la cara visible de la app: se abre como una ventana normal (sin consola),
deja editar los gestos, la sensibilidad, la camara y el tema, enseña la vista
previa de la camara y con un boton arranca la deteccion en un proceso aparte.
Asi conviven bien la GUI (tkinter) y la deteccion (OpenCV), que en el mismo
proceso se estorban.

La vista previa (ver vista.py) funciona como el preview de OBS: con la deteccion
parada abre la camara ella misma para que puedas encuadrarte, y con la deteccion
en marcha enseña los frames que publica el otro proceso, ya con el esqueleto, la
mira y el HUD dibujados.

Ejecutar sin consola:
    pythonw launcher.py     (o doble clic en Gestos.vbs)
"""

from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from pathlib import Path

import config
import grabador
import idiomas
import puente
import sistema
import vista


def carpeta_base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


RUTA_CONFIG = carpeta_base() / config.RUTA_DEFECTO_NOMBRE
RUTA_PREF_CAMARA = carpeta_base() / "config_camara.json"

# --------------------------------------------------------------------------- #
# Temas
# --------------------------------------------------------------------------- #

TEMAS = {
    "oscuro": {
        "fondo": "#16181d", "tarjeta": "#1f2229", "borde": "#2c313a",
        "texto": "#e8eaed", "sub": "#8b929e", "acento": "#5b9bff",
        "entrada": "#2a2f38", "ok": "#3ecf8e", "parado": "#6b7280",
        "primario": "#3b7dd8", "primario_txt": "#ffffff",
        "boton": "#2a2f38", "boton_txt": "#d7dae0",
    },
    "claro": {
        "fondo": "#f4f5f7", "tarjeta": "#ffffff", "borde": "#e0e2e7",
        "texto": "#1c1f24", "sub": "#6b7280", "acento": "#2f6fed",
        "entrada": "#eef0f4", "ok": "#0f9d63", "parado": "#9aa1ad",
        "primario": "#2f6fed", "primario_txt": "#ffffff",
        "boton": "#e8eaee", "boton_txt": "#2b2f36",
    },
}

# Icono textual de cada forma, para reconocerla de un vistazo en el editor.
ICONOS = {
    "un_dedo": "☝", "dos_dedos": "✌", "tres_dedos": "🖐",
    "pulgar": "👍", "mano_abierta": "✋", "puno": "✊",
    "pulgar_menique": "🤙",
}


class Launcher:
    """Ventana principal: edita la config y lanza la deteccion."""

    def __init__(self, raiz: tk.Tk) -> None:
        self.raiz = raiz
        self.proceso: subprocess.Popen | None = None
        self.cfg = config.cargar(RUTA_CONFIG)
        self.tema = self.cfg["tema"]
        self.t = idiomas.Textos(self.cfg["idioma"])
        # El registro manda sobre el archivo: si el usuario quito el arranque
        # automatico por fuera, la casilla debe reflejarlo.
        self.cfg["app"]["autoarranque"] = sistema.autoarranque_activo()
        self._traducibles: list[tuple] = []

        self.gestos_var: dict[str, tk.StringVar] = {}
        self.menus_gestos: list[tk.Menubutton] = []
        self._menus_desplegables: list[tk.Menu] = []
        self.botones_atajo: dict[str, tk.Widget] = {}
        self.botones_grabar: dict[str, tk.Button] = {}
        self._grabando: str | None = None      # gesto que se esta grabando
        self._grabador = None
        self._cargando = False                 # True mientras se vuelca la config
        self._pintables: list[tuple] = []
        self._tarjetas: list[tk.Frame] = []
        self._receptor = None                  # puente de frames con la deteccion

        raiz.title(self.t("titulo"))
        raiz.resizable(False, False)
        self._construir()
        self.cargar_en_ui(self.cfg)
        self._refrescar_atajos()
        self._aplicar_tema()
        raiz.protocol("WM_DELETE_WINDOW", self._cerrar)
        # Al minimizar se deja de pintar la vista previa: convertir 30 imagenes
        # por segundo para una ventana que no se ve le quita tiempo a la
        # deteccion, que es justo cuando el cursor se nota a tirones.
        raiz.bind("<Unmap>", self._ventana_oculta)
        raiz.bind("<Map>", self._ventana_visible)
        # Windows frena los procesos minimizados; aqui tambien se pide que no.
        sistema.mantener_ritmo()
        # La camara se abre despues de pintar la ventana: si se abriera antes,
        # la app tardaria un segundo largo en aparecer y pareceria colgada.
        raiz.after(300, self._vista_en_reposo)

    def _ventana_oculta(self, evento) -> None:
        # El evento tambien salta por widgets internos: solo interesa el de la
        # ventana entera.
        if evento.widget is self.raiz:
            self.vista.pausar()

    def _ventana_visible(self, evento) -> None:
        if evento.widget is self.raiz:
            self.vista.reanudar()

    # -- helpers de construccion ------------------------------------------- #

    def _reg(self, widget, bg, fg=None, clave=None, **extra) -> None:
        """Apunta un widget para recolorearlo al cambiar de tema.

        Con `clave` se apunta ademas para volver a traducirlo al cambiar de
        idioma, sin tener que reconstruir la ventana entera.
        """
        self._pintables.append((widget, bg, fg, extra))
        if clave:
            self._traducibles.append((widget, clave))

    def _retraducir(self) -> None:
        """Repinta todos los textos en el idioma actual."""
        for widget, clave in self._traducibles:
            try:
                widget.configure(text=self.t(clave))
            except tk.TclError:
                pass
        self.raiz.title(self.t("titulo"))
        self._modo_iniciar() if not self._deteccion_viva() else None
        self._refrescar_atajos()
        self.vista.retraducir(self.t)

    def _tarjeta(self, padre, clave: str) -> tk.Frame:
        """Bloque con titulo y un marco suave, para agrupar ajustes."""
        cab = tk.Label(padre, text=self.t(clave), anchor="w",
                       font=("Segoe UI", 8, "bold"))
        cab.pack(fill="x", pady=(14, 5))
        self._reg(cab, "fondo", "sub", clave=clave)

        marco = tk.Frame(padre, bd=1, relief="solid", padx=14, pady=12)
        marco.pack(fill="x")
        self._reg(marco, "tarjeta")
        self._tarjetas.append(marco)
        return marco

    # -- construccion de la interfaz --------------------------------------- #

    def _construir(self) -> None:
        cont = tk.Frame(self.raiz, padx=20, pady=16)
        cont.pack(fill="both", expand=True)
        self._reg(cont, "fondo")
        self._raiz_cont = cont

        # ---- Cabecera ---------------------------------------------------- #
        cab = tk.Frame(cont)
        cab.pack(fill="x")
        self._reg(cab, "fondo")

        titulo = tk.Label(cab, text=self.t("app_titulo"),
                          font=("Segoe UI", 17, "bold"))
        titulo.pack(side="left")
        self._reg(titulo, "fondo", "texto", clave="app_titulo")

        # Engranaje de ajustes, en la esquina superior derecha
        self.btn_ajustes = tk.Button(cab, text=self.t("ajustes"), width=11,
                                     relief="flat", bd=0, cursor="hand2",
                                     font=("Segoe UI", 9),
                                     command=self._abrir_ajustes)
        self.btn_ajustes.pack(side="right", pady=4, padx=(6, 0))
        self._reg(self.btn_ajustes, "boton", "boton_txt", clave="ajustes")

        self.btn_tema = tk.Button(cab, text="", width=11, relief="flat", bd=0,
                                  cursor="hand2", font=("Segoe UI", 9),
                                  command=self._alternar_tema)
        self.btn_tema.pack(side="right", pady=4)
        self._reg(self.btn_tema, "boton", "boton_txt")

        sub = tk.Label(cab, text="  " + self.t("app_sub"),
                       font=("Segoe UI", 10))
        sub.pack(side="left", pady=(6, 0))
        self._reg(sub, "fondo", "sub", clave="app_sub")

        # ---- Dos columnas ------------------------------------------------ #
        cuerpo = tk.Frame(cont)
        cuerpo.pack(fill="both", expand=True)
        self._reg(cuerpo, "fondo")

        izq = tk.Frame(cuerpo)
        izq.pack(side="left", fill="both", expand=True)
        self._reg(izq, "fondo")

        der = tk.Frame(cuerpo)
        der.pack(side="left", fill="both", expand=True, padx=(18, 0))
        self._reg(der, "fondo")

        # ---- Editor de gestos (izquierda) -------------------------------- #
        panel_g = self._tarjeta(izq, "sec_gestos")
        self.panel_gestos = panel_g
        for fila, fid in enumerate(config.FORMAS):
            ico = tk.Label(panel_g, text=ICONOS.get(fid, "•"),
                           font=("Segoe UI Emoji", 14), width=2)
            ico.grid(row=fila, column=0, sticky="w", pady=4)
            self._reg(ico, "tarjeta", "texto")

            lab = tk.Label(panel_g, text=config.etiqueta_forma(fid, self.t),
                           anchor="w", width=27, font=("Segoe UI", 10))
            lab.grid(row=fila, column=1, sticky="w", pady=4)
            self._reg(lab, "tarjeta", "texto", clave=f"forma_{fid}")

            # UN SOLO campo por gesto: muestra SIEMPRE lo que hace, sea una
            # accion de raton o una combinacion de teclas. Antes habia dos
            # controles y el de teclas ponia "—" en las acciones de raton, lo
            # que hacia parecer que no habia nada asignado.
            var = tk.StringVar()
            self.gestos_var[fid] = var
            var.trace_add("write", lambda *_, f=fid: self._menu_cambiado(f))
            om = self._menu_acciones(panel_g, var)
            om.grid(row=fila, column=2, sticky="w", pady=4, padx=(12, 0))
            self.menus_gestos.append(om)
            self.botones_atajo[fid] = om     # el propio campo refleja el estado

            # Boton de grabar: solo para teclas. Las acciones de raton se eligen
            # en el desplegable, porque no son combinaciones de teclado.
            grabar_btn = tk.Button(panel_g, text="⌨", width=3, bd=0,
                                   relief="flat", cursor="hand2",
                                   font=("Segoe UI", 10),
                                   command=lambda f=fid: self._grabar_en(f))
            grabar_btn.grid(row=fila, column=3, sticky="w", pady=4, padx=(6, 0))
            self.botones_grabar[fid] = grabar_btn
            self._reg(grabar_btn, "entrada", "texto")

            quitar = tk.Button(panel_g, text="✕", bd=0, relief="flat",
                               cursor="hand2", font=("Segoe UI", 8),
                               command=lambda f=fid: self._quitar_atajo(f))
            quitar.grid(row=fila, column=4, sticky="w", pady=4, padx=(4, 0))
            self._reg(quitar, "tarjeta", "sub")

        # ---- Sensibilidad (derecha) -------------------------------------- #
        panel_s = self._tarjeta(der, "sec_puntero")
        self.var_ganancia = tk.DoubleVar()
        self.var_acel = tk.DoubleVar()
        self._deslizador(panel_s, 0, "velocidad", self.var_ganancia,
                         0.5, 6.0, 0.1, "velocidad_pista")
        self._deslizador(panel_s, 3, "aceleracion", self.var_acel,
                         0.0, 4.0, 0.1, "aceleracion_pista")

        # ---- Camara (derecha) -------------------------------------------- #
        panel_c = self._tarjeta(der, "sec_camara")

        # La vista previa va dentro de la tarjeta de camara, encima de sus
        # casillas: es lo primero que se mira al elegir camara o al encuadrarse.
        self.vista = vista.VistaPrevia(panel_c, self.t)
        self.vista.marco.grid(row=0, column=0, columnspan=2, sticky="w",
                              pady=(0, 8))
        self.var_compartir = tk.BooleanVar()
        self.var_menu = tk.BooleanVar()
        self.checks = []
        for fila, (clave, var) in enumerate([
                ("compartir_camara", self.var_compartir),
                ("preguntar_camara", self.var_menu)]):
            chk = tk.Checkbutton(panel_c, text=self.t(clave), variable=var,
                                 anchor="w", font=("Segoe UI", 9), bd=0,
                                 highlightthickness=0, cursor="hand2")
            chk.grid(row=fila + 1, column=0, sticky="w", pady=2)
            self._reg(chk, "tarjeta", "texto", clave=clave, check=True)
            self.checks.append(chk)

        # ---- Como se asignan los atajos (izquierda) ----------------------- #
        nota = tk.Label(izq, anchor="w", justify="left", font=("Segoe UI", 9),
                        pady=8, text=self.t("pista_gestos"))
        nota.pack(fill="x")
        self._reg(nota, "fondo", "sub", clave="pista_gestos")

        # ---- Ayuda (derecha) --------------------------------------------- #
        panel_a = self._tarjeta(der, "sec_ayuda")
        lab_a = tk.Label(panel_a, text=self.t("ayuda_deteccion"), justify="left",
                         anchor="w", font=("Segoe UI", 9))
        lab_a.pack(fill="x")
        self._reg(lab_a, "tarjeta", "sub", clave="ayuda_deteccion")

        # ---- Pie: estado + botones --------------------------------------- #
        pie = tk.Frame(cont)
        pie.pack(fill="x", pady=(18, 0))
        self._reg(pie, "fondo")

        self.punto = tk.Label(pie, text="●", font=("Segoe UI", 13))
        self.punto.pack(side="left")
        self._reg(self.punto, "fondo", "parado")

        self.estado = tk.Label(pie, text=self.t("estado_detenido"), font=("Segoe UI", 9),
                               anchor="w")
        self.estado.pack(side="left", padx=(6, 0))
        self._reg(self.estado, "fondo", "sub")

        btn_reset = tk.Button(pie, text=self.t("restablecer"), width=12, relief="flat",
                              bd=0, cursor="hand2", font=("Segoe UI", 9),
                              command=self._restablecer)
        btn_reset.pack(side="right", padx=(8, 0))
        self._reg(btn_reset, "boton", "boton_txt")

        btn_guardar = tk.Button(pie, text=self.t("guardar"), width=11, relief="flat",
                                bd=0, cursor="hand2", font=("Segoe UI", 9),
                                command=self._guardar)
        btn_guardar.pack(side="right", padx=(8, 0))
        self._reg(btn_guardar, "boton", "boton_txt")

        self.btn_iniciar = tk.Button(pie, text=self.t("iniciar"), width=14, bd=0,
                                     font=("Segoe UI", 11, "bold"),
                                     relief="flat", cursor="hand2",
                                     command=self._iniciar_o_parar)
        self.btn_iniciar.pack(side="right")
        self._reg(self.btn_iniciar, "primario", "primario_txt")

    def _menu_acciones(self, padre, var: tk.StringVar) -> tk.Menubutton:
        """Selector de accion con submenus por categoria.

        Con mas de 30 atajos una lista plana seria inservible, asi que cada
        grupo (Ventanas, Multimedia..., y "Mis atajos") abre su propio submenu.
        """
        etiqueta = dict(config.acciones(self.cfg, self.t))
        boton = tk.Menubutton(padre, textvariable=var, width=24, anchor="w",
                              relief="flat", bd=0, highlightthickness=0,
                              font=("Segoe UI", 9), cursor="hand2",
                              indicatoron=True)
        menu = tk.Menu(boton, tearoff=0)
        boton.configure(menu=menu)
        self._menus_desplegables.append(menu)

        for titulo, ids in config.grupos(self.cfg, self.t):
            sub = tk.Menu(menu, tearoff=0)
            self._menus_desplegables.append(sub)
            for aid in ids:
                if aid not in etiqueta:
                    continue
                sub.add_command(
                    label=etiqueta[aid],
                    command=lambda v=var, t=etiqueta[aid]: v.set(t))
            menu.add_cascade(label=titulo, menu=sub)
        return boton

    # -- grabacion de atajos, al estilo Discord ----------------------------- #

    def _grabar_en(self, fid: str) -> None:
        """Graba un atajo directamente sobre la fila del gesto (in situ).

        Como los keybinds de Discord: pulsas el boton, teclea la combinacion y
        queda asignada. Sin dialogos ni pasos intermedios.
        """
        if self._grabando is not None:       # ya hay una grabacion en marcha
            self._parar_grabacion()
            return

        self._grabando = fid
        self.gestos_var[fid].set(self.t("estado_pulsa"))
        self._pintar_grabacion(fid, True)

        self._grabador = grabador.GrabadorAtajos()

        if not self._grabador.iniciar():
            self._grabador = None
            self._grabando = None
            self._pintar_grabacion(fid, False)
            self._refrescar_atajos()
            self.estado.configure(
                text=self.t("estado_sin_teclado"))
            return

        self._sondear_grabacion(fid)

    def _sondear_grabacion(self, fid: str) -> None:
        """Recoge lo grabado desde el bucle de tk, nunca desde el hook.

        El hook se ejecuta dentro del despacho de mensajes de Windows; tocar
        tkinter desde ahi puede tumbar el proceso, porque Tcl no es reentrante.
        Por eso el hook solo deja el resultado y aqui se consulta.
        """
        if self._grabando != fid or self._grabador is None:
            return
        if self._grabador.cancelado:
            self._parar_grabacion()
            self.estado.configure(text=self.t("estado_cancelado"))
            return
        teclas = self._grabador.capturado
        if teclas is not None:
            self._grabador.capturado = None
            self._asignar_atajo(fid, teclas)
            return
        self.raiz.after(30, lambda: self._sondear_grabacion(fid))

    def _asignar_atajo(self, fid: str, teclas) -> None:
        """Guarda la combinacion recien grabada y la asigna a ese gesto."""
        self._parar_grabacion()
        aid = config.id_propio(teclas)
        self.cfg.setdefault("atajos_propios", {})[aid] = {
            "nombre": grabador.describir(teclas), "teclas": list(teclas)}
        self.cfg["gestos"][fid] = aid
        config.guardar(RUTA_CONFIG, self.cfg)
        self.cfg = config.cargar(RUTA_CONFIG)
        self.cargar_en_ui(self.cfg)
        self._refrescar_atajos()
        self.estado.configure(
            text=f"{config.etiqueta_forma(fid, self.t)} → {grabador.describir(teclas)}")

    def _parar_grabacion(self) -> None:
        if self._grabador is not None:
            self._grabador.detener()
            self._grabador = None
        if self._grabando is not None:
            self._pintar_grabacion(self._grabando, False)
            self._grabando = None
        self._refrescar_atajos()

    def _pintar_grabacion(self, fid: str, activo: bool) -> None:
        """Resalta el campo y el boton mientras se esta grabando ese gesto."""
        t = TEMAS[self.tema]
        for widget in (self.botones_atajo.get(fid), self.botones_grabar.get(fid)):
            if widget is not None:
                widget.configure(bg=t["primario"] if activo else t["entrada"],
                                 fg=t["primario_txt"] if activo else t["texto"])

    def _quitar_atajo(self, fid: str) -> None:
        """Deja el gesto sin accion."""
        self.cfg["gestos"][fid] = "nada"
        self.gestos_var[fid].set(config.etiqueta_accion("nada", self.t))
        config.guardar(RUTA_CONFIG, self.cfg)
        self._refrescar_atajos()
        self.estado.configure(text=self.t("estado_sin_asignar", gesto=config.etiqueta_forma(fid, self.t)))

    def _menu_cambiado(self, fid: str) -> None:
        """El usuario eligio una accion en el menu: se refleja en el recuadro."""
        if self._cargando or self._grabando is not None:
            return
        por_etiqueta = {et: aid for aid, et in config.acciones(self.cfg, self.t)}
        aid = por_etiqueta.get(self.gestos_var[fid].get())
        if aid:
            self.cfg["gestos"][fid] = aid
            self._refrescar_atajos()

    def _refrescar_atajos(self) -> None:
        """Sincroniza el campo de cada gesto con lo que hay en la config.

        El campo muestra siempre la accion, sea de raton ("Clic derecho") o una
        combinacion grabada ("Ctrl + M"): un unico sitio donde mirar.
        """
        if self._grabando is not None:
            return
        etiquetas = dict(config.acciones(self.cfg, self.t))
        self._cargando = True
        for fid in self.gestos_var:
            accion = self.cfg["gestos"].get(fid, "nada")
            self.gestos_var[fid].set(etiquetas.get(accion, config.etiqueta_accion("nada", self.t)))
            self._pintar_grabacion(fid, False)
        self._cargando = False

    def _deslizador(self, padre, fila, clave, var, desde, hasta, paso,
                    clave_pista) -> None:
        lab = tk.Label(padre, text=self.t(clave), anchor="w",
                       font=("Segoe UI", 10))
        lab.grid(row=fila, column=0, sticky="w")
        self._reg(lab, "tarjeta", "texto", clave=clave)

        esc = tk.Scale(padre, variable=var, from_=desde, to=hasta,
                       resolution=paso, orient="horizontal", length=250,
                       showvalue=True, relief="flat", bd=0,
                       highlightthickness=0, font=("Segoe UI", 8),
                       sliderrelief="flat")
        esc.grid(row=fila + 1, column=0, sticky="w")
        self._reg(esc, "tarjeta", "texto", escala=True)

        hint = tk.Label(padre, text=self.t(clave_pista), anchor="w",
                        font=("Segoe UI", 8))
        hint.grid(row=fila + 2, column=0, sticky="w", pady=(0, 10))
        self._reg(hint, "tarjeta", "sub", clave=clave_pista)

    # -- temas -------------------------------------------------------------- #

    def _aplicar_tema(self) -> None:
        t = TEMAS[self.tema]
        self.raiz.configure(bg=t["fondo"])
        for widget, bg, fg, extra in self._pintables:
            op = {"bg": t[bg]}
            if fg:
                op["fg"] = t[fg]
            if extra.get("check"):
                op.update(selectcolor=t["entrada"], activebackground=t[bg],
                          activeforeground=t[fg])
            if extra.get("escala"):
                op.update(troughcolor=t["entrada"], activebackground=t["acento"],
                          highlightbackground=t["tarjeta"])
            try:
                widget.configure(**op)
            except tk.TclError:
                pass

        for marco in self._tarjetas:
            marco.configure(highlightbackground=t["borde"],
                            highlightcolor=t["borde"], bg=t["tarjeta"])

        for om in self.menus_gestos:
            om.configure(bg=t["entrada"], fg=t["texto"],
                         activebackground=t["acento"],
                         activeforeground=t["primario_txt"],
                         highlightthickness=0)
        for menu in self._menus_desplegables:
            menu.configure(bg=t["entrada"], fg=t["texto"],
                           activebackground=t["acento"],
                           activeforeground=t["primario_txt"], bd=0)
        self.btn_tema.configure(
            text=self.t("tema_claro") if self.tema == "oscuro" else self.t("tema_oscuro"))
        # La vista previa se queda oscura en los dos temas: es una imagen, y un
        # marco blanco alrededor falsea los colores de lo que estas mirando (por
        # eso el preview de OBS es negro pase lo que pase).
        self.vista.aplicar_tema(t)
        self._pintar_estado()

    def _alternar_tema(self) -> None:
        self.tema = "claro" if self.tema == "oscuro" else "oscuro"
        self._aplicar_tema()

    def _pintar_estado(self) -> None:
        t = TEMAS[self.tema]
        vivo = self._deteccion_viva()
        self.punto.configure(fg=t["ok"] if vivo else t["parado"])

    # -- config <-> interfaz ----------------------------------------------- #

    def cargar_en_ui(self, cfg: dict) -> None:
        """Vuelca una configuracion en los controles de la ventana."""
        self._cargando = True                # evita que el trace pise la config
        etiqueta_accion = dict(config.acciones(cfg, self.t))
        for fid, var in self.gestos_var.items():
            var.set(etiqueta_accion.get(cfg["gestos"][fid], self.t("accion_nada")))
        self._cargando = False
        self.var_ganancia.set(cfg["sensibilidad"]["ganancia"])
        self.var_acel.set(cfg["sensibilidad"]["aceleracion"])
        self.var_compartir.set(cfg["camara"]["compartir"])
        self.var_menu.set(cfg["camara"]["menu_siempre"])
        self.tema = cfg["tema"]

    def leer_config(self) -> dict:
        """Construye la configuracion a partir del estado actual de la ventana."""
        accion_por_etiqueta = {et: aid for aid, et in config.acciones(self.cfg, self.t)}
        cfg = config.por_defecto()
        cfg["tema"] = self.tema
        # Los atajos grabados no estan en ningun control: se arrastran tal cual
        cfg["atajos_propios"] = dict(self.cfg.get("atajos_propios", {}))
        for fid, var in self.gestos_var.items():
            cfg["gestos"][fid] = accion_por_etiqueta.get(var.get(), "nada")
        cfg["sensibilidad"]["ganancia"] = round(self.var_ganancia.get(), 2)
        cfg["sensibilidad"]["aceleracion"] = round(self.var_acel.get(), 2)
        cfg["camara"]["compartir"] = bool(self.var_compartir.get())
        cfg["camara"]["menu_siempre"] = bool(self.var_menu.get())
        cfg["camara"]["indice"] = self.cfg["camara"]["indice"]   # se conserva
        return cfg

    # -- acciones de los botones ------------------------------------------- #

    def _guardar(self) -> dict:
        cfg = self.leer_config()
        config.guardar(RUTA_CONFIG, cfg)
        self.cfg = cfg
        self.estado.configure(text=self.t("estado_guardado"))
        return cfg

    def _restablecer(self) -> None:
        self.cargar_en_ui(config.por_defecto())
        self._aplicar_tema()
        self.estado.configure(text=self.t("estado_fabrica"))

    def _interprete(self) -> str:
        """Ruta a pythonw (sin consola) o, en su defecto, al python actual."""
        py = Path(sys.executable)
        pyw = py.with_name("pythonw.exe")
        return str(pyw if pyw.exists() else py)

    def _deteccion_viva(self) -> bool:
        return self.proceso is not None and self.proceso.poll() is None

    def _iniciar_o_parar(self) -> None:
        if self._deteccion_viva():
            self.proceso.terminate()
            self.proceso = None
            self._soltar_vista()
            self._modo_iniciar()
            self._vista_en_reposo()          # vuelve la camara a la vista previa
            self.estado.configure(text=self.t("estado_detenido"))
            return

        self._guardar()          # la deteccion lee config.json al arrancar

        # La camara la va a abrir el otro proceso, asi que hay que SOLTARLA
        # antes de lanzarlo: en Windows una webcam normal no se abre dos veces,
        # y si la vista previa la sigue teniendo, la deteccion arranca y muere
        # diciendo que no hay camara.
        self.vista.parar_camara()

        orden = [self._interprete(), str(carpeta_base() / "gestos_manos.py")]
        try:
            self._receptor = puente.Receptor()
            orden += ["--vista", self._receptor.nombre]
        except (OSError, ValueError):
            self._receptor = None            # sin vista previa, pero detecta

        self.proceso = subprocess.Popen(orden, cwd=str(carpeta_base()))
        if self._receptor is not None:
            self.vista.escuchar(self._receptor)
            self.vista.marcar(True)
        self.btn_iniciar.configure(text=self.t("detener"))
        self.estado.configure(text=self.t("estado_marcha"))
        self._pintar_estado()
        self.raiz.after(1500, self._vigilar)

    def _soltar_vista(self) -> None:
        """Corta el puente con la deteccion y libera la memoria compartida."""
        self.vista.dejar_de_escuchar()
        self.vista.marcar(False)
        if self._receptor is not None:
            self._receptor.cerrar()
            self._receptor = None

    def _vista_en_reposo(self) -> None:
        """Vuelve a enseñar la camara en directo, si la vista previa esta activa."""
        self.vista.parar()
        if self.cfg["deteccion"].get("vista_previa", True):
            self.vista.arrancar_camara(self.cfg, RUTA_PREF_CAMARA)

    def _modo_iniciar(self) -> None:
        self.btn_iniciar.configure(text=self.t("iniciar"))
        self._pintar_estado()

    def _vigilar(self) -> None:
        """Si la deteccion termina sola, vuelve a dejar el boton en 'Iniciar'."""
        if self._deteccion_viva():
            self.raiz.after(1500, self._vigilar)
        elif self.proceso is not None:
            self.proceso = None
            self._soltar_vista()
            self._modo_iniciar()
            self._vista_en_reposo()      # la camara vuelve a estar libre
            self.estado.configure(text=self.t("estado_cerrado"))

    # -- ventana de ajustes ------------------------------------------------- #

    def _abrir_ajustes(self) -> None:
        """Panel con todos los ajustes de la aplicacion."""
        t, T = TEMAS[self.tema], self.t
        dlg = tk.Toplevel(self.raiz)
        dlg.title(T("ajustes_titulo"))
        dlg.configure(bg=t["fondo"])
        dlg.resizable(False, False)
        dlg.transient(self.raiz)
        dlg.grab_set()

        cont = tk.Frame(dlg, bg=t["fondo"], padx=22, pady=16)
        cont.pack(fill="both", expand=True)

        # Estas variables viven mientras el dialogo este abierto
        v = {
            "idioma": tk.StringVar(value=dict(idiomas.IDIOMAS)[self.cfg["idioma"]]),
            "tema": tk.StringVar(value=self.cfg["tema"]),
            "resolucion": tk.StringVar(value=self.cfg["deteccion"]["resolucion"]),
        }
        for clave in ("autoarranque", "arrancar_minimizado", "detectar_al_abrir",
                      "confirmar_salida", "sonido"):
            v[clave] = tk.BooleanVar(value=self.cfg["app"][clave])
        for clave in ("espejo", "estela", "mostrar_ventana", "hud",
                      "vista_previa"):
            v[clave] = tk.BooleanVar(value=self.cfg["deteccion"][clave])
        for clave in ("espera_atajo", "espera_control"):
            v[clave] = tk.DoubleVar(value=self.cfg["deteccion"][clave])

        def seccion(titulo):
            lab = tk.Label(cont, text=titulo.upper(), bg=t["fondo"], fg=t["sub"],
                           font=("Segoe UI", 8, "bold"), anchor="w")
            lab.pack(fill="x", pady=(12, 4))
            marco = tk.Frame(cont, bg=t["tarjeta"], bd=1, relief="solid",
                             padx=12, pady=8)
            marco.configure(highlightbackground=t["borde"])
            marco.pack(fill="x")
            return marco

        def casilla(padre, texto, var, pista=""):
            tk.Checkbutton(padre, text=texto, variable=var, anchor="w",
                           bg=t["tarjeta"], fg=t["texto"], selectcolor=t["entrada"],
                           activebackground=t["tarjeta"], activeforeground=t["texto"],
                           bd=0, highlightthickness=0, cursor="hand2",
                           font=("Segoe UI", 9)).pack(fill="x", pady=1)
            if pista:
                tk.Label(padre, text=pista, bg=t["tarjeta"], fg=t["sub"],
                         font=("Segoe UI", 8), anchor="w").pack(fill="x",
                                                                padx=(22, 0))

        def desplegable(padre, texto, var, opciones):
            fila = tk.Frame(padre, bg=t["tarjeta"])
            fila.pack(fill="x", pady=2)
            tk.Label(fila, text=texto, bg=t["tarjeta"], fg=t["texto"],
                     font=("Segoe UI", 9), width=22, anchor="w").pack(side="left")
            om = tk.OptionMenu(fila, var, *opciones)
            om.configure(bg=t["entrada"], fg=t["texto"], bd=0, width=16,
                         highlightthickness=0, anchor="w", cursor="hand2",
                         activebackground=t["acento"], font=("Segoe UI", 9))
            om["menu"].configure(bg=t["entrada"], fg=t["texto"], bd=0,
                                 activebackground=t["acento"])
            om.pack(side="left")

        def deslizador(padre, texto, var, desde, hasta, paso):
            fila = tk.Frame(padre, bg=t["tarjeta"])
            fila.pack(fill="x", pady=2)
            tk.Label(fila, text=texto, bg=t["tarjeta"], fg=t["texto"],
                     font=("Segoe UI", 9), width=30, anchor="w").pack(side="left")
            tk.Scale(fila, variable=var, from_=desde, to=hasta, resolution=paso,
                     orient="horizontal", length=150, bg=t["tarjeta"],
                     fg=t["texto"], troughcolor=t["entrada"], bd=0,
                     highlightthickness=0, font=("Segoe UI", 8),
                     activebackground=t["acento"]).pack(side="left")

        # --- General ---
        g1 = seccion(T("aj_general"))
        desplegable(g1, T("aj_idioma"), v["idioma"],
                    [n for _, n in idiomas.IDIOMAS])
        desplegable(g1, T("aj_tema"), v["tema"], ["oscuro", "claro"])
        casilla(g1, T("aj_inicio"), v["autoarranque"], T("aj_inicio_pista"))
        casilla(g1, T("aj_minimizado"), v["arrancar_minimizado"])
        casilla(g1, T("aj_autodeteccion"), v["detectar_al_abrir"])
        casilla(g1, T("aj_confirmar"), v["confirmar_salida"])

        # --- Deteccion ---
        g2 = seccion(T("aj_deteccion"))
        casilla(g2, T("aj_espejo"), v["espejo"])
        casilla(g2, T("aj_estela"), v["estela"])
        casilla(g2, T("aj_ventana"), v["mostrar_ventana"])
        casilla(g2, T("aj_vista"), v["vista_previa"], T("aj_vista_pista"))
        casilla(g2, T("aj_hud"), v["hud"], T("aj_hud_pista"))
        desplegable(g2, T("aj_resolucion"), v["resolucion"], config.RESOLUCIONES)

        # --- Tiempos ---
        g3 = seccion(T("aj_tiempos"))
        deslizador(g3, T("aj_espera_atajo"), v["espera_atajo"], 0.1, 2.0, 0.05)
        deslizador(g3, T("aj_espera_control"), v["espera_control"], 0.3, 5.0, 0.1)

        # --- Avisos ---
        g4 = seccion(T("aj_avisos"))
        casilla(g4, T("aj_sonido"), v["sonido"])

        # --- Ayuda ---
        g5 = seccion(T("aj_ayuda"))
        for texto, accion in (
                (T("aj_github"), lambda: sistema.abrir(idiomas.URL_GITHUB)),
                (T("aj_manual"),
                 lambda: sistema.abrir(idiomas.URL_GITHUB + "#chuleta-de-gestos")),
                (T("aj_carpeta"),
                 lambda: sistema.abrir(str(carpeta_base())))):
            tk.Button(g5, text=texto, command=accion, anchor="w", bd=0,
                      relief="flat", cursor="hand2", bg=t["tarjeta"],
                      fg=t["acento"], activebackground=t["tarjeta"],
                      font=("Segoe UI", 9)).pack(fill="x", pady=1)
        tk.Label(g5, text=T("aj_version", v=idiomas.VERSION), bg=t["tarjeta"],
                 fg=t["sub"], font=("Segoe UI", 8), anchor="w").pack(fill="x",
                                                                     pady=(6, 0))

        # --- Botones ---
        pie = tk.Frame(cont, bg=t["fondo"])
        pie.pack(fill="x", pady=(16, 0))

        def aplicar() -> None:
            nombre_a_id = {n: i for i, n in idiomas.IDIOMAS}
            self.cfg["idioma"] = nombre_a_id.get(v["idioma"].get(), "es")
            self.cfg["tema"] = v["tema"].get()
            for clave in ("arrancar_minimizado", "detectar_al_abrir",
                          "confirmar_salida", "sonido"):
                self.cfg["app"][clave] = bool(v[clave].get())
            for clave in ("espejo", "estela", "mostrar_ventana", "hud",
                          "vista_previa"):
                self.cfg["deteccion"][clave] = bool(v[clave].get())
            self.cfg["deteccion"]["resolucion"] = v["resolucion"].get()
            for clave in ("espera_atajo", "espera_control"):
                self.cfg["deteccion"][clave] = round(v[clave].get(), 2)

            # El autoarranque se escribe en el registro: se guarda lo que de
            # verdad quedo, no lo que se pidio.
            self.cfg["app"]["autoarranque"] = sistema.sincronizar_autoarranque(
                bool(v["autoarranque"].get()))

            config.guardar(RUTA_CONFIG, self.cfg)
            self.cfg = config.cargar(RUTA_CONFIG)
            self.tema = self.cfg["tema"]
            self.t.cambiar(self.cfg["idioma"])
            dlg.grab_release()
            dlg.destroy()
            self._retraducir()
            self._aplicar_tema()
            # Reabrir la vista previa: aqui se pueden haber cambiado el espejo,
            # la resolucion o la propia casilla de la vista, y todo eso hay que
            # aplicarlo a la camara que ya estaba abierta.
            if not self._deteccion_viva():
                self._vista_en_reposo()
            self.estado.configure(text=self.t("estado_guardado"))

        tk.Button(pie, text=T("aceptar"), command=aplicar, bd=0, width=12,
                  bg=t["primario"], fg=t["primario_txt"], relief="flat",
                  cursor="hand2", font=("Segoe UI", 10, "bold")).pack(side="right")
        tk.Button(pie, text=T("cancelar"), bd=0, width=10, relief="flat",
                  cursor="hand2", bg=t["boton"], fg=t["boton_txt"],
                  font=("Segoe UI", 10),
                  command=lambda: (dlg.grab_release(), dlg.destroy())
                  ).pack(side="right", padx=8)

        dlg.update_idletasks()
        x = self.raiz.winfo_rootx() + (self.raiz.winfo_width()
                                       - dlg.winfo_width()) // 2
        dlg.geometry(f"+{max(0, x)}+{max(0, self.raiz.winfo_rooty() + 30)}")

    def _cerrar(self) -> None:
        if self.cfg["app"]["confirmar_salida"]:
            from tkinter import messagebox
            if not messagebox.askokcancel(self.t("titulo"),
                                          self.t("confirmar_salir")):
                return
        self._parar_grabacion()   # nunca dejar el hook de teclado instalado
        if self._deteccion_viva():
            self.proceso.terminate()
        self.vista.parar()        # suelta la camara y para el hilo lector
        self._soltar_vista()
        self.raiz.destroy()


def main() -> None:
    raiz = tk.Tk()
    Launcher(raiz)
    raiz.mainloop()


if __name__ == "__main__":
    main()
