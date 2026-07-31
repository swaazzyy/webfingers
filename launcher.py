"""
Launcher grafico del detector de gestos.

Es la cara visible de la app: se abre como una ventana normal (sin consola),
deja editar los gestos, la sensibilidad, la camara y el tema, y con un boton
arranca la deteccion en un proceso aparte. Asi conviven bien la GUI (tkinter) y
la deteccion (OpenCV), que en el mismo proceso se estorban.

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


def carpeta_base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


RUTA_CONFIG = carpeta_base() / config.RUTA_DEFECTO_NOMBRE

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

        raiz.title("Gestos · Control por camara")
        raiz.resizable(False, False)
        self._construir()
        self.cargar_en_ui(self.cfg)
        self._refrescar_atajos()
        self._aplicar_tema()
        raiz.protocol("WM_DELETE_WINDOW", self._cerrar)

    # -- helpers de construccion ------------------------------------------- #

    def _reg(self, widget, bg, fg=None, **extra) -> None:
        """Apunta un widget para recolorearlo al cambiar de tema."""
        self._pintables.append((widget, bg, fg, extra))

    def _tarjeta(self, padre, titulo: str) -> tk.Frame:
        """Bloque con titulo y un marco suave, para agrupar ajustes."""
        cab = tk.Label(padre, text=titulo.upper(), anchor="w",
                       font=("Segoe UI", 8, "bold"))
        cab.pack(fill="x", pady=(14, 5))
        self._reg(cab, "fondo", "sub")

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

        titulo = tk.Label(cab, text="Control por gestos",
                          font=("Segoe UI", 17, "bold"))
        titulo.pack(side="left")
        self._reg(titulo, "fondo", "texto")

        self.btn_tema = tk.Button(cab, text="", width=11, relief="flat", bd=0,
                                  cursor="hand2", font=("Segoe UI", 9),
                                  command=self._alternar_tema)
        self.btn_tema.pack(side="right", pady=4)
        self._reg(self.btn_tema, "boton", "boton_txt")

        sub = tk.Label(cab, text="  mueve el cursor con la mano",
                       font=("Segoe UI", 10))
        sub.pack(side="left", pady=(6, 0))
        self._reg(sub, "fondo", "sub")

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
        panel_g = self._tarjeta(izq, "Gestos  ·  elige que hace cada mano")
        self.panel_gestos = panel_g
        for fila, (fid, fetiqueta) in enumerate(config.FORMAS):
            ico = tk.Label(panel_g, text=ICONOS.get(fid, "•"),
                           font=("Segoe UI Emoji", 14), width=2)
            ico.grid(row=fila, column=0, sticky="w", pady=4)
            self._reg(ico, "tarjeta", "texto")

            lab = tk.Label(panel_g, text=fetiqueta, anchor="w", width=27,
                           font=("Segoe UI", 10))
            lab.grid(row=fila, column=1, sticky="w", pady=4)
            self._reg(lab, "tarjeta", "texto")

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
        panel_s = self._tarjeta(der, "Puntero")
        self.var_ganancia = tk.DoubleVar()
        self.var_acel = tk.DoubleVar()
        self._deslizador(panel_s, 0, "Velocidad", self.var_ganancia,
                         0.5, 6.0, 0.1, "lento y preciso ←→ rapido")
        self._deslizador(panel_s, 3, "Aceleracion", self.var_acel,
                         0.0, 4.0, 0.1, "empuje extra en gestos amplios")

        # ---- Camara (derecha) -------------------------------------------- #
        panel_c = self._tarjeta(der, "Camara")
        self.var_compartir = tk.BooleanVar()
        self.var_menu = tk.BooleanVar()
        self.checks = []
        for fila, (texto, var) in enumerate([
                ("Compartir con otras apps (Zoom, Teams…)", self.var_compartir),
                ("Preguntar que camara usar al arrancar", self.var_menu)]):
            chk = tk.Checkbutton(panel_c, text=texto, variable=var, anchor="w",
                                 font=("Segoe UI", 9), bd=0,
                                 highlightthickness=0, cursor="hand2")
            chk.grid(row=fila, column=0, sticky="w", pady=2)
            self._reg(chk, "tarjeta", "texto", check=True)
            self.checks.append(chk)

        # ---- Como se asignan los atajos (izquierda) ----------------------- #
        nota = tk.Label(
            izq, anchor="w", justify="left", font=("Segoe UI", 9), pady=8,
            text="Despliega para elegir raton o un atajo ya hecho.   ⌨ graba la "
                 "combinacion\nde teclas que quieras (incluida la tecla "
                 "Windows).   ✕ deja el gesto sin asignar.")
        nota.pack(fill="x")
        self._reg(nota, "fondo", "sub")

        # ---- Ayuda (derecha) --------------------------------------------- #
        panel_a = self._tarjeta(der, "Mientras detecta")
        ayuda = ("La ventana de camara no muestra texto.\n"
                 "Salir de la deteccion:  tecla  Q  o cerrar la ventana.\n"
                 "El gesto de on/off pausa el control sin cerrar nada.")
        lab_a = tk.Label(panel_a, text=ayuda, justify="left", anchor="w",
                         font=("Segoe UI", 9))
        lab_a.pack(fill="x")
        self._reg(lab_a, "tarjeta", "sub")

        # ---- Pie: estado + botones --------------------------------------- #
        pie = tk.Frame(cont)
        pie.pack(fill="x", pady=(18, 0))
        self._reg(pie, "fondo")

        self.punto = tk.Label(pie, text="●", font=("Segoe UI", 13))
        self.punto.pack(side="left")
        self._reg(self.punto, "fondo", "parado")

        self.estado = tk.Label(pie, text="Detenido", font=("Segoe UI", 9),
                               anchor="w")
        self.estado.pack(side="left", padx=(6, 0))
        self._reg(self.estado, "fondo", "sub")

        btn_reset = tk.Button(pie, text="Restablecer", width=12, relief="flat",
                              bd=0, cursor="hand2", font=("Segoe UI", 9),
                              command=self._restablecer)
        btn_reset.pack(side="right", padx=(8, 0))
        self._reg(btn_reset, "boton", "boton_txt")

        btn_guardar = tk.Button(pie, text="Guardar", width=11, relief="flat",
                                bd=0, cursor="hand2", font=("Segoe UI", 9),
                                command=self._guardar)
        btn_guardar.pack(side="right", padx=(8, 0))
        self._reg(btn_guardar, "boton", "boton_txt")

        self.btn_iniciar = tk.Button(pie, text="▶  Iniciar", width=14, bd=0,
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
        etiqueta = dict(config.acciones(self.cfg))
        boton = tk.Menubutton(padre, textvariable=var, width=24, anchor="w",
                              relief="flat", bd=0, highlightthickness=0,
                              font=("Segoe UI", 9), cursor="hand2",
                              indicatoron=True)
        menu = tk.Menu(boton, tearoff=0)
        boton.configure(menu=menu)
        self._menus_desplegables.append(menu)

        for titulo, ids in config.grupos(self.cfg):
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
        self.gestos_var[fid].set("Pulsa las teclas…")
        self._pintar_grabacion(fid, True)

        self._grabador = grabador.GrabadorAtajos()

        if not self._grabador.iniciar():
            self._grabador = None
            self._grabando = None
            self._pintar_grabacion(fid, False)
            self._refrescar_atajos()
            self.estado.configure(
                text="No se pudo capturar el teclado en este equipo")
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
            self.estado.configure(text="Grabacion cancelada")
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
            text=f"{config.ETIQUETA_FORMA[fid]} → {grabador.describir(teclas)}")

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
        self.gestos_var[fid].set("🚫 Nada")
        config.guardar(RUTA_CONFIG, self.cfg)
        self._refrescar_atajos()
        self.estado.configure(text=f"{config.ETIQUETA_FORMA[fid]} sin asignar")

    def _menu_cambiado(self, fid: str) -> None:
        """El usuario eligio una accion en el menu: se refleja en el recuadro."""
        if self._cargando or self._grabando is not None:
            return
        por_etiqueta = {et: aid for aid, et in config.acciones(self.cfg)}
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
        etiquetas = dict(config.acciones(self.cfg))
        self._cargando = True
        for fid in self.gestos_var:
            accion = self.cfg["gestos"].get(fid, "nada")
            self.gestos_var[fid].set(etiquetas.get(accion, "🚫 Nada"))
            self._pintar_grabacion(fid, False)
        self._cargando = False

    def _deslizador(self, padre, fila, texto, var, desde, hasta, paso,
                    pista) -> None:
        lab = tk.Label(padre, text=texto, anchor="w", font=("Segoe UI", 10))
        lab.grid(row=fila, column=0, sticky="w")
        self._reg(lab, "tarjeta", "texto")

        esc = tk.Scale(padre, variable=var, from_=desde, to=hasta,
                       resolution=paso, orient="horizontal", length=250,
                       showvalue=True, relief="flat", bd=0,
                       highlightthickness=0, font=("Segoe UI", 8),
                       sliderrelief="flat")
        esc.grid(row=fila + 1, column=0, sticky="w")
        self._reg(esc, "tarjeta", "texto", escala=True)

        hint = tk.Label(padre, text=pista, anchor="w", font=("Segoe UI", 8))
        hint.grid(row=fila + 2, column=0, sticky="w", pady=(0, 10))
        self._reg(hint, "tarjeta", "sub")

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
            text="☀  Claro" if self.tema == "oscuro" else "🌙  Oscuro")
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
        etiqueta_accion = dict(config.acciones(cfg))
        for fid, var in self.gestos_var.items():
            var.set(etiqueta_accion.get(cfg["gestos"][fid], "🚫 Nada"))
        self._cargando = False
        self.var_ganancia.set(cfg["sensibilidad"]["ganancia"])
        self.var_acel.set(cfg["sensibilidad"]["aceleracion"])
        self.var_compartir.set(cfg["camara"]["compartir"])
        self.var_menu.set(cfg["camara"]["menu_siempre"])
        self.tema = cfg["tema"]

    def leer_config(self) -> dict:
        """Construye la configuracion a partir del estado actual de la ventana."""
        accion_por_etiqueta = {et: aid for aid, et in config.acciones(self.cfg)}
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
        self.estado.configure(text="Configuracion guardada")
        return cfg

    def _restablecer(self) -> None:
        self.cargar_en_ui(config.por_defecto())
        self._aplicar_tema()
        self.estado.configure(text="Valores de fabrica (sin guardar)")

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
            self._modo_iniciar()
            self.estado.configure(text="Detenido")
            return

        self._guardar()          # la deteccion lee config.json al arrancar
        script = carpeta_base() / "gestos_manos.py"
        self.proceso = subprocess.Popen([self._interprete(), str(script)],
                                        cwd=str(carpeta_base()))
        self.btn_iniciar.configure(text="■  Detener")
        self.estado.configure(text="En marcha · ponte frente a la camara")
        self._pintar_estado()
        self.raiz.after(1500, self._vigilar)

    def _modo_iniciar(self) -> None:
        self.btn_iniciar.configure(text="▶  Iniciar")
        self._pintar_estado()

    def _vigilar(self) -> None:
        """Si la deteccion termina sola, vuelve a dejar el boton en 'Iniciar'."""
        if self._deteccion_viva():
            self.raiz.after(1500, self._vigilar)
        elif self.proceso is not None:
            self.proceso = None
            self._modo_iniciar()
            self.estado.configure(text="La deteccion se cerro")

    def _cerrar(self) -> None:
        self._parar_grabacion()   # nunca dejar el hook de teclado instalado
        if self._deteccion_viva():
            self.proceso.terminate()
        self.raiz.destroy()


def main() -> None:
    raiz = tk.Tk()
    Launcher(raiz)
    raiz.mainloop()


if __name__ == "__main__":
    main()
