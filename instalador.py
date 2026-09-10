"""
Instalador grafico de Control por gestos.

Pregunta carpeta e idioma, copia los archivos, crea los accesos directos y deja
la aplicacion lista. No necesita permisos de administrador porque instala en la
carpeta del usuario (%LOCALAPPDATA%) y usa HKCU para el arranque automatico.

    python instalador.py          (o el .exe generado con construir_exe.bat)
"""

from __future__ import annotations

import os
import shutil
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import idiomas
import sistema

# Lo que se copia a la carpeta de instalacion. El modelo se incluye si esta:
# asi la app funciona sin conexion desde el primer arranque.
ARCHIVOS = [
    "launcher.py", "gestos_manos.py", "control_windows.py", "camara.py",
    "config.py", "grabador.py", "hud.py", "idiomas.py", "puente.py",
    "sistema.py", "vista.py",
    "requirements.txt", "README.md", "hand_landmarker.task",
    # Lanzadores y preparacion del entorno en el equipo de destino. Los dos .bat
    # van a proposito: el .venv NO se copia (es del equipo que lo creo), asi que
    # el usuario tiene que poder rehacerlo donde instale.
    "Gestos.vbs", "iniciar.bat", "preparar_entorno.bat",
]

TEMA = {
    "fondo": "#16181d", "tarjeta": "#1f2229", "borde": "#2c313a",
    "texto": "#e8eaed", "sub": "#8b929e", "acento": "#5b9bff",
    "entrada": "#2a2f38", "primario": "#3b7dd8", "primario_txt": "#ffffff",
    "boton": "#2a2f38", "boton_txt": "#d7dae0", "ok": "#3ecf8e",
    "error": "#ff6b6b",
}


def origen() -> Path:
    """Carpeta de donde se copian los archivos (junto al instalador)."""
    if getattr(sys, "frozen", False):
        # Empaquetado: PyInstaller extrae los datos en _MEIPASS
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).parent


def destino_por_defecto() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / "ControlPorGestos"


def tamano_mb() -> int:
    total = sum((origen() / a).stat().st_size
                for a in ARCHIVOS if (origen() / a).exists())
    return max(1, round(total / (1024 * 1024)))


class Instalador:
    def __init__(self, raiz: tk.Tk) -> None:
        self.raiz = raiz
        self.t = idiomas.Textos(idiomas.POR_DEFECTO)
        t = TEMA

        raiz.title(self.t("inst_titulo"))
        raiz.configure(bg=t["fondo"])
        raiz.resizable(False, False)

        cont = tk.Frame(raiz, bg=t["fondo"], padx=28, pady=22)
        cont.pack(fill="both", expand=True)

        self.lb_titulo = tk.Label(cont, text=self.t("inst_bienvenida"),
                                  bg=t["fondo"], fg=t["texto"],
                                  font=("Segoe UI", 18, "bold"), anchor="w")
        self.lb_titulo.pack(fill="x")
        self.lb_intro = tk.Label(cont, text=self.t("inst_intro"), bg=t["fondo"],
                                 fg=t["sub"], font=("Segoe UI", 10),
                                 justify="left", anchor="w")
        self.lb_intro.pack(fill="x", pady=(4, 16))

        # --- Idioma ------------------------------------------------------- #
        fila_idioma = tk.Frame(cont, bg=t["fondo"])
        fila_idioma.pack(fill="x", pady=(0, 10))
        self.lb_idioma = tk.Label(fila_idioma, text=self.t("inst_idioma"),
                                  bg=t["fondo"], fg=t["texto"],
                                  font=("Segoe UI", 10), width=22, anchor="w")
        self.lb_idioma.pack(side="left")
        self.var_idioma = tk.StringVar(value=idiomas.IDIOMAS[0][1])
        om = tk.OptionMenu(fila_idioma, self.var_idioma,
                           *[n for _, n in idiomas.IDIOMAS],
                           command=lambda *_: self._retraducir())
        om.configure(bg=t["entrada"], fg=t["texto"], bd=0, width=14,
                     highlightthickness=0, anchor="w", cursor="hand2",
                     activebackground=t["acento"], font=("Segoe UI", 9))
        om["menu"].configure(bg=t["entrada"], fg=t["texto"], bd=0,
                             activebackground=t["acento"])
        om.pack(side="left")

        # --- Carpeta ------------------------------------------------------- #
        self.lb_carpeta = tk.Label(cont, text=self.t("inst_carpeta"),
                                   bg=t["fondo"], fg=t["texto"],
                                   font=("Segoe UI", 10), anchor="w")
        self.lb_carpeta.pack(fill="x")
        fila = tk.Frame(cont, bg=t["fondo"])
        fila.pack(fill="x", pady=(4, 4))
        self.var_ruta = tk.StringVar(value=str(destino_por_defecto()))
        tk.Entry(fila, textvariable=self.var_ruta, width=46, bd=0,
                 bg=t["entrada"], fg=t["texto"], insertbackground=t["texto"],
                 font=("Segoe UI", 10), relief="flat").pack(side="left",
                                                            ipady=6)
        self.btn_examinar = tk.Button(fila, text=self.t("inst_examinar"), bd=0,
                                      bg=t["boton"], fg=t["boton_txt"],
                                      relief="flat", cursor="hand2",
                                      font=("Segoe UI", 9),
                                      command=self._elegir_carpeta)
        self.btn_examinar.pack(side="left", padx=(8, 0), ipady=4)
        self.lb_espacio = tk.Label(cont, text=self.t("inst_espacio",
                                                     mb=tamano_mb()),
                                   bg=t["fondo"], fg=t["sub"],
                                   font=("Segoe UI", 8), anchor="w")
        self.lb_espacio.pack(fill="x", pady=(0, 12))

        # --- Opciones ------------------------------------------------------ #
        self.opciones = {}
        self.checks = {}
        for clave, defecto in (("inst_acceso", True), ("inst_menu", True),
                               ("inst_autoarranque", False),
                               ("inst_abrir", True)):
            var = tk.BooleanVar(value=defecto)
            self.opciones[clave] = var
            chk = tk.Checkbutton(cont, text=self.t(clave), variable=var,
                                 bg=t["fondo"], fg=t["texto"], anchor="w",
                                 selectcolor=t["entrada"], bd=0,
                                 activebackground=t["fondo"],
                                 activeforeground=t["texto"],
                                 highlightthickness=0, cursor="hand2",
                                 font=("Segoe UI", 9))
            chk.pack(fill="x", pady=1)
            self.checks[clave] = chk

        # --- Pie ----------------------------------------------------------- #
        self.estado = tk.Label(cont, text="", bg=t["fondo"], fg=t["sub"],
                               font=("Segoe UI", 9), anchor="w")
        self.estado.pack(fill="x", pady=(14, 6))

        pie = tk.Frame(cont, bg=t["fondo"])
        pie.pack(fill="x")
        self.btn_instalar = tk.Button(pie, text=self.t("inst_instalar"), bd=0,
                                      width=16, bg=t["primario"],
                                      fg=t["primario_txt"], relief="flat",
                                      cursor="hand2",
                                      font=("Segoe UI", 11, "bold"),
                                      command=self._instalar)
        self.btn_instalar.pack(side="right", ipady=4)
        self.btn_cancelar = tk.Button(pie, text=self.t("cancelar"), bd=0,
                                      width=12, bg=t["boton"],
                                      fg=t["boton_txt"], relief="flat",
                                      cursor="hand2", font=("Segoe UI", 10),
                                      command=raiz.destroy)
        self.btn_cancelar.pack(side="right", padx=8, ipady=4)

    # -- acciones ----------------------------------------------------------- #

    def _retraducir(self) -> None:
        ident = {n: i for i, n in idiomas.IDIOMAS}
        self.t.cambiar(ident.get(self.var_idioma.get(), "es"))
        self.raiz.title(self.t("inst_titulo"))
        self.lb_titulo.configure(text=self.t("inst_bienvenida"))
        self.lb_intro.configure(text=self.t("inst_intro"))
        self.lb_idioma.configure(text=self.t("inst_idioma"))
        self.lb_carpeta.configure(text=self.t("inst_carpeta"))
        self.lb_espacio.configure(text=self.t("inst_espacio", mb=tamano_mb()))
        self.btn_examinar.configure(text=self.t("inst_examinar"))
        self.btn_instalar.configure(text=self.t("inst_instalar"))
        self.btn_cancelar.configure(text=self.t("cancelar"))
        for clave, chk in self.checks.items():
            chk.configure(text=self.t(clave))

    def _elegir_carpeta(self) -> None:
        elegida = filedialog.askdirectory(initialdir=self.var_ruta.get())
        if elegida:
            self.var_ruta.set(str(Path(elegida)))

    def _instalar(self) -> None:
        self.estado.configure(text=self.t("inst_instalando"), fg=TEMA["sub"])
        self.raiz.update()
        try:
            destino = instalar(
                Path(self.var_ruta.get()),
                idioma={n: i for i, n in idiomas.IDIOMAS}[self.var_idioma.get()],
                acceso_escritorio=self.opciones["inst_acceso"].get(),
                menu_inicio=self.opciones["inst_menu"].get(),
                autoarranque=self.opciones["inst_autoarranque"].get())
        except Exception as e:                             # noqa: BLE001
            self.estado.configure(text=self.t("inst_error", e=e),
                                  fg=TEMA["error"])
            return

        self.estado.configure(text=self.t("inst_listo"), fg=TEMA["ok"])
        self.btn_instalar.configure(state="disabled")
        if self.opciones["inst_abrir"].get():
            sistema.abrir(str(destino / "Gestos.vbs"))
        self.raiz.after(1200, self.raiz.destroy)


# --------------------------------------------------------------------------- #
# Instalacion (sin interfaz, para poder probarla)
# --------------------------------------------------------------------------- #

def instalar(destino: Path, idioma: str, acceso_escritorio: bool,
             menu_inicio: bool, autoarranque: bool) -> Path:
    """Copia la aplicacion y deja los accesos creados. Devuelve la carpeta."""
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)

    faltan = [a for a in ARCHIVOS
              if not (origen() / a).exists() and a != "hand_landmarker.task"]
    if faltan:
        raise FileNotFoundError(f"faltan archivos de origen: {faltan}")

    for archivo in ARCHIVOS:
        src = origen() / archivo
        if src.exists():
            shutil.copy2(src, destino / archivo)

    # Config inicial con el idioma elegido (respeta una instalacion anterior)
    import config
    ruta_cfg = destino / config.RUTA_DEFECTO_NOMBRE
    cfg = config.cargar(ruta_cfg)
    cfg["idioma"] = idioma
    cfg["app"]["autoarranque"] = autoarranque
    config.guardar(ruta_cfg, cfg)

    lanzador = destino / "Gestos.vbs"
    if acceso_escritorio:
        sistema.crear_acceso(sistema.escritorio() / "Control por gestos.lnk",
                             objetivo=str(lanzador),
                             carpeta_trabajo=str(destino))
    if menu_inicio:
        sistema.crear_acceso(
            sistema.menu_inicio() / "Control por gestos.lnk",
            objetivo=str(lanzador), carpeta_trabajo=str(destino))
    if autoarranque:
        sistema.activar_autoarranque(f'wscript.exe "{lanzador}"')
    else:
        sistema.desactivar_autoarranque()
    return destino


def main() -> None:
    raiz = tk.Tk()
    Instalador(raiz)
    raiz.eval("tk::PlaceWindow . center")
    raiz.mainloop()


if __name__ == "__main__":
    main()
