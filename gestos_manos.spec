# PyInstaller spec para el detector de gestos.
#
# Construir con:   .venv\Scripts\pyinstaller.exe gestos_manos.spec
# (o simplemente:  construir_exe.bat)
#
# MediaPipe trae binarios y archivos de datos (.binarypb, .tflite) que hay que
# recolectar explicitamente; collect_all se encarga de datos + binarios + los
# imports ocultos. Se genera en modo "onedir": una carpeta dist\GestosManos con
# el .exe y sus dependencias. Es la forma mas fiable con MediaPipe (el modo
# onefile a veces falla al cargar sus DLL nativas).

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for paquete in ("mediapipe",):
    d, b, h = collect_all(paquete)
    datas += d
    binaries += b
    hiddenimports += h

# El modelo NO se empaqueta dentro (PyInstaller lo pondria en _internal, donde
# el programa no lo busca). construir_exe.bat lo copia junto al .exe tras la
# compilacion; si aun asi faltara, el programa lo descarga solo en el arranque.

block_cipher = None

a = Analysis(
    ["gestos_manos.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["mediapipe.tasks.python.vision"],
    hookspath=[],
    runtime_hooks=[],
    # matplotlib lo importa mediapipe.tasks.vision.drawing_utils, asi que NO se
    # puede excluir aunque nuestro codigo no lo use directamente.
    excludes=["pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GestosManos",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,        # deja la consola para ver errores; ver README para ocultarla
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="GestosManos",
)
