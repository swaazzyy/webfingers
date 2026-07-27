"""
Launcher grafico del detector de gestos.

Es la cara visible de la app: se abre como una ventana normal (sin consola),
deja editar los gestos, la sensibilidad, la camara y el tema, y con un boton
arranca la deteccion en un proceso aparte. Asi conviven bien la GUI (tkinter) y
la deteccion (OpenCV), que en el mismo proceso se estorban.

Ejecutar sin consola:
    pythonw launcher.py     (o doble clic en iniciar.bat)
"""

from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from pathlib import Path

import config


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
        "fondo": "#1e1e1e", "panel": "#2a2a2a", "texto": "#e6e6e6",
        "sub": "#9a9a9a", "acento": "#4c8cff", "entrada": "#3a3a3a",
        "boton": "#3a6ea5", "boton_txt": "#ffffff",
        "boton2": "#444444", "boton2_txt": "#e6e6e6",
    },
    "claro": {
        "fondo": "#f2f3f5", "panel": "#ffffff", "texto": "#1b1b1b",
        "sub": "#666666", "acento": "#2f6fed", "entrada": "#ececf0",
        "boton": "#2f6fed", "boton_txt": "#ffffff",
        "boton2": "#e2e2e6", "boton2_txt": "#1b1b1b",
    },
}


class Launcher:
    """Ventana principal: edita la config y lanza la deteccion."""

    def __init__(self, raiz: tk.Tk) -> None:
        self.raiz = raiz
        self.proceso: subprocess.Popen | None = None
        self.cfg = config.cargar(RUTA_CONFIG)
        self.tema = self.cfg["tema"]

        self.gestos_var: dict[str, tk.StringVar] = {}
        self.menus_gestos: list[tk.OptionMenu] = []
        self._pintables: list[tuple[tk.Widget, str, str]] = []  # (widget, bg, fg)

        raiz.title("Gestos - Control por camara")
        raiz.resizable(False, False)
        self._construir()
        self.cargar_en_ui(self.cfg)
        self._aplicar_tema()
        raiz.protocol("WM_DELETE_WINDOW", self._cerrar)

    # -- construccion de la interfaz --------------------------------------- #

    def _construir(self) -> None:
        cont = tk.Frame(self.raiz, padx=18, pady=16)
        cont.pack(fill="both", expand=True)
        self._marco_fondo = cont

        # Cabecera con el titulo y el conmutador de tema
        cab = tk.Frame(cont)
        cab.pack(fill="x", pady=(0, 12))
        self._reg(cab, "fondo")
        titulo = tk.Label(cab, text="Control por gestos", font=("Segoe UI", 16, "bold"))
        titulo.pack(side="left")
        self._reg(titulo, "fondo", "texto")
        self.btn_tema = tk.Button(cab, text="", width=10, relief="flat",
                                  command=self._alternar_tema, cursor="hand2")
        self.btn_tema.pack(side="right")
        self._reg(self.btn_tema, "boton2", "boton2_txt")

        # --- Editor de gestos --------------------------------------------- #
        self._titulo_seccion(cont, "Gestos")
        panel_g = tk.Frame(cont, padx=12, pady=10)
        panel_g.pack(fill="x")
        self._reg(panel_g, "panel")
        acciones_lbl = [et for _, et in config.ACCIONES]
        for fila, (fid, fetiqueta) in enumerate(config.FORMAS):
            lab = tk.Label(panel_g, text=fetiqueta, anchor="w", width=30,
                           font=("Segoe UI", 10))
            lab.grid(row=fila, column=0, sticky="w", pady=3)
            self._reg(lab, "panel", "texto")

            var = tk.StringVar()
            self.gestos_var[fid] = var
            om = tk.OptionMenu(panel_g, var, *acciones_lbl)
            om.config(width=22, relief="flat", highlightthickness=0, anchor="w")
            om.grid(row=fila, column=1, sticky="w", pady=3, padx=(10, 0))
            self.menus_gestos.append(om)

        # --- Sensibilidad -------------------------------------------------- #
        self._titulo_seccion(cont, "Sensibilidad del puntero")
        panel_s = tk.Frame(cont, padx=12, pady=8)
        panel_s.pack(fill="x")
        self._reg(panel_s, "panel")
        self.var_ganancia = tk.DoubleVar()
        self.var_acel = tk.DoubleVar()
        self._deslizador(panel_s, 0, "Velocidad", self.var_ganancia, 0.5, 6.0, 0.1)
        self._deslizador(panel_s, 1, "Aceleracion", self.var_acel, 0.0, 4.0, 0.1)

        # --- Camara -------------------------------------------------------- #
        self._titulo_seccion(cont, "Camara")
        panel_c = tk.Frame(cont, padx=12, pady=8)
        panel_c.pack(fill="x")
        self._reg(panel_c, "panel")
        self.var_compartir = tk.BooleanVar()
        self.var_menu = tk.BooleanVar()
        c1 = tk.Checkbutton(panel_c, text="Compartir la camara con otras apps "
                            "(Zoom, Teams...)", variable=self.var_compartir,
                            anchor="w")
        c1.grid(row=0, column=0, sticky="w")
        c2 = tk.Checkbutton(panel_c, text="Preguntar que camara usar en cada "
                            "arranque", variable=self.var_menu, anchor="w")
        c2.grid(row=1, column=0, sticky="w")
        for chk in (c1, c2):
            self._reg(chk, "panel", "texto", check=True)
        self.checks_camara = (c1, c2)

        # --- Botones ------------------------------------------------------- #
        pie = tk.Frame(cont)
        pie.pack(fill="x", pady=(16, 0))
        self._reg(pie, "fondo")
        self.btn_iniciar = tk.Button(pie, text="Iniciar", width=14,
                                     font=("Segoe UI", 11, "bold"), relief="flat",
                                     cursor="hand2", command=self._iniciar_o_parar)
        self.btn_iniciar.pack(side="left")
        self._reg(self.btn_iniciar, "boton", "boton_txt")

        btn_guardar = tk.Button(pie, text="Guardar", width=12, relief="flat",
                                cursor="hand2", command=self._guardar)
        btn_guardar.pack(side="left", padx=8)
        self._reg(btn_guardar, "boton2", "boton2_txt")

        btn_reset = tk.Button(pie, text="Restablecer", width=12, relief="flat",
                              cursor="hand2", command=self._restablecer)
        btn_reset.pack(side="left")
        self._reg(btn_reset, "boton2", "boton2_txt")

        self.estado = tk.Label(cont, text="", font=("Segoe UI", 9))
        self.estado.pack(anchor="w", pady=(10, 0))
        self._reg(self.estado, "fondo", "sub")

    def _titulo_seccion(self, padre, texto) -> None:
        lab = tk.Label(padre, text=texto, font=("Segoe UI", 11, "bold"),
                       anchor="w")
        lab.pack(fill="x", pady=(14, 4))
        self._reg(lab, "fondo", "acento")

    def _deslizador(self, padre, fila, texto, var, desde, hasta, paso) -> None:
        lab = tk.Label(padre, text=texto, width=12, anchor="w")
        lab.grid(row=fila, column=0, sticky="w", pady=2)
        self._reg(lab, "panel", "texto")
        esc = tk.Scale(padre, variable=var, from_=desde, to=hasta,
                       resolution=paso, orient="horizontal", length=260,
                       showvalue=True, relief="flat", highlightthickness=0)
        esc.grid(row=fila, column=1, sticky="w", padx=(8, 0))
        self._reg(esc, "panel", "texto", escala=True)

    def _reg(self, widget, bg, fg=None, check=False, escala=False) -> None:
        """Apunta un widget para poder recolorearlo al cambiar de tema."""
        self._pintables.append((widget, bg, fg, check, escala))

    # -- temas -------------------------------------------------------------- #

    def _aplicar_tema(self) -> None:
        t = TEMAS[self.tema]
        self.raiz.configure(bg=t["fondo"])
        self._marco_fondo.configure(bg=t["fondo"])
        for widget, bg, fg, check, escala in self._pintables:
            opciones = {"bg": t[bg]}
            if fg:
                opciones["fg"] = t[fg]
            if check:
                opciones.update(selectcolor=t["entrada"],
                                activebackground=t[bg], activeforeground=t[fg])
            if escala:
                opciones.update(troughcolor=t["entrada"], activebackground=t["acento"],
                                highlightbackground=t["panel"])
            try:
                widget.configure(**opciones)
            except tk.TclError:
                pass

        # Los OptionMenu y su menu desplegable van aparte
        for om in self.menus_gestos:
            om.configure(bg=t["entrada"], fg=t["texto"], activebackground=t["acento"],
                         activeforeground=t["boton_txt"], highlightthickness=0)
            om["menu"].configure(bg=t["entrada"], fg=t["texto"],
                                 activebackground=t["acento"],
                                 activeforeground=t["boton_txt"])
        self.btn_tema.configure(
            text="Tema claro" if self.tema == "oscuro" else "Tema oscuro")

    def _alternar_tema(self) -> None:
        self.tema = "claro" if self.tema == "oscuro" else "oscuro"
        self._aplicar_tema()

    # -- config <-> interfaz ----------------------------------------------- #

    def cargar_en_ui(self, cfg: dict) -> None:
        """Vuelca una configuracion en los controles de la ventana."""
        etiqueta_accion = dict(config.ACCIONES)
        for fid, var in self.gestos_var.items():
            var.set(etiqueta_accion[cfg["gestos"][fid]])
        self.var_ganancia.set(cfg["sensibilidad"]["ganancia"])
        self.var_acel.set(cfg["sensibilidad"]["aceleracion"])
        self.var_compartir.set(cfg["camara"]["compartir"])
        self.var_menu.set(cfg["camara"]["menu_siempre"])
        self.tema = cfg["tema"]

    def leer_config(self) -> dict:
        """Construye la configuracion a partir del estado actual de la ventana."""
        accion_por_etiqueta = {et: aid for aid, et in config.ACCIONES}
        cfg = config.por_defecto()
        cfg["tema"] = self.tema
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
        self.estado.configure(text="Configuracion guardada.")
        return cfg

    def _restablecer(self) -> None:
        defecto = config.por_defecto()
        self.cargar_en_ui(defecto)
        self._aplicar_tema()
        self.estado.configure(text="Valores por defecto restaurados (sin guardar).")

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
            self.estado.configure(text="Deteccion detenida.")
            return

        self._guardar()          # la deteccion lee config.json al arrancar
        script = carpeta_base() / "gestos_manos.py"
        self.proceso = subprocess.Popen([self._interprete(), str(script)],
                                        cwd=str(carpeta_base()))
        self.btn_iniciar.configure(text="Detener")
        self.estado.configure(text="Deteccion en marcha. Ponte frente a la camara.")
        self.raiz.after(1500, self._vigilar)

    def _modo_iniciar(self) -> None:
        self.btn_iniciar.configure(text="Iniciar")

    def _vigilar(self) -> None:
        """Si la deteccion termina sola, vuelve a dejar el boton en 'Iniciar'."""
        if self._deteccion_viva():
            self.raiz.after(1500, self._vigilar)
        elif self.proceso is not None:
            self.proceso = None
            self._modo_iniciar()
            self.estado.configure(text="La deteccion se cerro.")

    def _cerrar(self) -> None:
        if self._deteccion_viva():
            self.proceso.terminate()
        self.raiz.destroy()


def main() -> None:
    raiz = tk.Tk()
    Launcher(raiz)
    raiz.mainloop()


if __name__ == "__main__":
    main()
