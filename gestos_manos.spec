# PyInstaller: genera DOS ejecutables.
#
#   dist/ControlPorGestos/ControlPorGestos.exe  -> la aplicacion
#   dist/InstalarControlPorGestos.exe           -> el instalador (un solo .exe)
#
# Construir con:  construir_exe.bat
#
# MediaPipe trae binarios y datos (.binarypb, .tflite) que hay que recolectar
# explicitamente; collect_all se encarga de datos + binarios + imports ocultos.
# La app va en modo "onedir" (carpeta con el .exe) porque con MediaPipe es lo
# mas fiable: en onefile a veces falla al cargar sus DLL nativas. El instalador
# si es onefile: es pequeno y asi se reparte como un unico archivo.

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for paquete in ("mediapipe",):
    d, b, h = collect_all(paquete)
    datas += d
    binaries += b
    hiddenimports += h

block_cipher = None

# --------------------------------------------------------------------------- #
# 1) La aplicacion
# --------------------------------------------------------------------------- #
a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["mediapipe.tasks.python.vision"],
    hookspath=[],
    runtime_hooks=[],
    # matplotlib lo importa mediapipe.tasks.vision.drawing_utils, asi que NO se
    # puede excluir aunque el codigo no lo use.
    excludes=["pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ControlPorGestos",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # aplicacion con ventana: sin consola negra
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=True,
               upx_exclude=[], name="ControlPorGestos")

# --------------------------------------------------------------------------- #
# 2) El instalador: lleva dentro los archivos que va a copiar
# --------------------------------------------------------------------------- #
FUENTES = ["launcher.py", "gestos_manos.py", "control_windows.py", "camara.py",
           "config.py", "grabador.py", "hud.py", "idiomas.py", "sistema.py",
           "requirements.txt", "README.md", "Gestos.vbs"]

datos_inst = [(f, ".") for f in FUENTES]
import os
if os.path.exists("hand_landmarker.task"):
    datos_inst.append(("hand_landmarker.task", "."))

a_inst = Analysis(
    ["instalador.py"],
    pathex=[],
    binaries=[],
    datas=datos_inst,
    hiddenimports=["config", "idiomas", "sistema"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["mediapipe", "cv2", "matplotlib", "numpy", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz_inst = PYZ(a_inst.pure, a_inst.zipped_data, cipher=block_cipher)

exe_inst = EXE(
    pyz_inst, a_inst.scripts, a_inst.binaries, a_inst.zipfiles, a_inst.datas, [],
    name="InstalarControlPorGestos",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,          # el instalador tambien es una ventana
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
