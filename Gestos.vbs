' Lanzador del launcher grafico SIN ninguna ventana de consola.
' Doble clic aqui y se abre directamente la ventana de la aplicacion.
'
' Busca un interprete que SIRVA de verdad, en este orden:
'   1) el entorno virtual de la carpeta, pero solo si esta sano;
'   2) el Python del sistema (pythonw, sin consola);
'   3) si no hay ninguno, lo dice con un mensaje que se entiende.
'
' El punto 1 es importante: un .venv trae sus propios .exe, pero son un
' REDIRECTOR que lanza el Python de verdad guardado en pyvenv.cfg. Si la carpeta
' se copia a otro equipo, a otro usuario o a otra unidad, esos .exe siguen ahi
' pero apuntan a una ruta que ya no existe, y Windows suelta un cuadro de error
' ("did not find executable at C:\Users\<otro>\...\pythonw.exe") en vez de
' arrancar. Comprobando antes que el interprete base sigue en su sitio, un
' entorno heredado se ignora y la app tira del Python del sistema.
Option Explicit

Dim fso, sh, base, pyw
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
base = fso.GetParentFolderName(WScript.ScriptFullName)

pyw = Interprete(base)

If pyw = "" Then
    MsgBox "No se encontro Python en este equipo." & vbCrLf & vbCrLf & _
           "1) Instalalo desde https://www.python.org/downloads/" & vbCrLf & _
           "2) Haz doble clic en preparar_entorno.bat, en esta misma carpeta." _
           , vbExclamation, "Control por gestos"
    WScript.Quit 1
End If

sh.CurrentDirectory = base
' El 0 final oculta cualquier ventana; False = no esperar a que termine.
sh.Run """" & pyw & """ """ & base & "\launcher.py""", 0, False


Function Interprete(carpeta)
    ' Primer interprete utilizable, o "" si no hay ninguno.
    Dim propio
    propio = carpeta & "\.venv\Scripts\pythonw.exe"
    If fso.FileExists(propio) Then
        If EntornoSano(carpeta & "\.venv") Then
            Interprete = propio
            Exit Function
        End If
    End If
    Interprete = EnElPath("pythonw.exe")
    If Interprete = "" Then Interprete = EnElPath("pyw.exe")
End Function


Function EntornoSano(entorno)
    ' True si el Python base al que apunta el entorno virtual sigue existiendo.
    Dim cfg, f, partes
    EntornoSano = False
    cfg = entorno & "\pyvenv.cfg"
    If Not fso.FileExists(cfg) Then Exit Function

    Set f = fso.OpenTextFile(cfg, 1)
    Do Until f.AtEndOfStream
        partes = Split(f.ReadLine, "=", 2)
        If UBound(partes) = 1 Then
            If LCase(Trim(partes(0))) = "home" Then
                EntornoSano = fso.FolderExists(Trim(partes(1)))
                Exit Do
            End If
        End If
    Loop
    f.Close
End Function


Function EnElPath(nombre)
    ' Busca un ejecutable por el PATH sin abrir ninguna consola (nada de "where",
    ' que haria parpadear una ventana negra justo en el lanzador silencioso).
    Dim rutas, i, candidato
    EnElPath = ""
    rutas = Split(sh.ExpandEnvironmentStrings("%PATH%"), ";")
    For i = 0 To UBound(rutas)
        If Len(Trim(rutas(i))) > 0 Then
            candidato = fso.BuildPath(Trim(rutas(i)), nombre)
            If fso.FileExists(candidato) Then
                ' Los "alias de ejecucion" de la Microsoft Store ocupan 0 bytes
                ' y lo unico que hacen es abrir la tienda: no son un Python.
                If fso.GetFile(candidato).Size > 0 Then
                    EnElPath = candidato
                    Exit Function
                End If
            End If
        End If
    Next
End Function
