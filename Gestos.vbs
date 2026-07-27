' Lanzador del launcher grafico SIN ninguna ventana de consola.
' Doble clic aqui y se abre directamente la ventana de la aplicacion.
Option Explicit
Dim fso, sh, base, pyw
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")
base = fso.GetParentFolderName(WScript.ScriptFullName)

' Preferir el pythonw del entorno virtual; si no, el del sistema.
pyw = base & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(pyw) Then pyw = "pythonw.exe"

sh.CurrentDirectory = base
' El 0 final oculta cualquier ventana; False = no esperar a que termine.
sh.Run """" & pyw & """ """ & base & "\launcher.py""", 0, False
