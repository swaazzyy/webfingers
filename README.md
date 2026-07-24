# Detector de gestos de mano (MediaPipe + OpenCV)

Detección en tiempo real desde la webcam, con esqueleto de mano superpuesto.
El dedo **mueve el cursor real de Windows** (air-mouse relativo) y abrir/cerrar
la mano **hace zoom en la ventana activa**. Todo se maneja con las manos.

## Chuleta de gestos

> **En pantalla no aparece ninguna indicación.** Solo se ve el esqueleto de la
> mano y la diana del puntero. Esta tabla es la única referencia — tenla a mano
> las primeras veces.

Los gestos se distinguen por el **número de dedos estirados**. Nada de juntar
puntas ni medir separaciones: cuentas dedos y ya está.

| Dedos | Gesto | Qué hace |
|:---:|---|---|
| **1** ☝️ | índice | **mueve el cursor** de Windows |
| **2** ✌️ | índice + medio | **clic izquierdo** — mantén y mueve para **arrastrar** |
| **3** 🖖 | índice + medio + anular | **clic derecho** |
| **5** ✋ | mano abierta | **acercar** (zoom in), sostenido |
| **0** ✊ | puño | **alejar** (zoom out), sostenido |
| 👍 | solo el pulgar, hacia arriba | mantén **1,2 s**: activa/desactiva el control |
| 🤙 | pulgar + meñique | mantén **2 s**: **salir** del programa |

El pulgar da igual al apuntar y al hacer clic: `1 dedo` y `1 dedo + pulgar` (la
"L") hacen lo mismo. Cualquier otra forma no hace nada.

## Archivos

- [gestos_manos.py](gestos_manos.py) — detección, clasificación y bucle principal
- [control_windows.py](control_windows.py) — movimiento del cursor y zoom (SendInput)

## Instalación

El entorno ya está creado en `.venv` (Python 3.13). Si necesitas rehacerlo:

```bash
py -3.13 -m venv .venv && .venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Ejecución

Doble clic en **`iniciar.bat`**, o desde la terminal:

```bash
.venv\Scripts\python.exe gestos_manos.py
```

Con el control activado (arranca en ON), levanta **un dedo** y mueve la mano: el
**cursor de Windows** se desplaza. Sobre la imagen de la cámara verás la diana y
una estela del dedo como referencia; su longitud se ajusta con `LARGO_ESTELA`.

La ventana no muestra texto alguno — ni FPS, ni nombres de gestos, ni ayuda. Si
no recuerdas un gesto, mira la [chuleta](#chuleta-de-gestos) de arriba.

Teclas de respaldo (solo funcionan si la ventana de la cámara tiene el foco):
`q`/`ESC` salir, `c` activar o desactivar el control.

El modelo `hand_landmarker.task` (~7 MB) ya está descargado en la carpeta; si se
borra, el script lo vuelve a bajar solo en el siguiente arranque.

## Crear un ejecutable (.exe)

Para tener la app como programa independiente que se abre con doble clic —sin
terminal, sin `.venv`, en su propia ventana— se empaqueta con PyInstaller:

```bash
construir_exe.bat
```

Genera `dist\GestosManos\GestosManos.exe`. Ese es el archivo que abres; la
carpeta que lo acompaña (`_internal`, ~265 MB por los binarios de MediaPipe)
tiene que viajar **junto** al `.exe`: para llevártelo a otro PC, copia la carpeta
`GestosManos` entera, no solo el `.exe`. No necesita Python instalado en el
equipo de destino.

Comprobar que un `.exe` quedó bien empaquetado, sin necesidad de cámara:

```bash
dist\GestosManos\GestosManos.exe --selftest
```

Debe imprimir *"OK: mediapipe cargo el modelo y proceso un frame."*

### Ventana con o sin consola

Tal cual, al abrirlo aparecen **dos ventanas**: una consola negra (donde se ven
mensajes y errores) y la ventana de la cámara. Si prefieres que salga **solo la
ventana de la cámara**, edita `gestos_manos.spec`, cambia `console=True` por
`console=False` y vuelve a ejecutar `construir_exe.bat`. Ojo: sin consola, si
algo falla no verás el motivo, así que conviene dejar la consola hasta
comprobar que todo va fino.

Notas de empaquetado que resolví por el camino: MediaPipe necesita que se
recojan sus binarios y datos (`collect_all` en el `.spec`) e importa
`matplotlib` por dentro (no se puede excluir aunque el código no lo use); y el
modelo `hand_landmarker.task` se copia junto al `.exe` porque PyInstaller lo
metería en `_internal`, donde el programa no lo busca. Si aun así faltara, se
descarga solo en el primer arranque.

## El puntero: air-mouse relativo (mueve el cursor real)

Con el gesto de **apuntar** (solo el índice), el **cursor real de Windows** se
mueve según *cuánto* desplaces la mano, no según dónde la pongas — igual que un
ratón o un trackpad. Funciona en cualquier programa.

Si bajas la mano y vuelves a apuntar, el cursor **continúa donde estaba**: al
retomar el gesto el programa se re-ancla a la posición real del cursor, así que
es el efecto de "levantar el ratón para recolocarlo" (embrague). No hay ningún
recuadro que mapear: mueves, sueltas, recolocas, sigues.

Lleva una **aceleración** como la del ratón de Windows: los movimientos lentos
avanzan poco (control fino) y los rápidos avanzan mucho (llegas de un lado a otro
de la pantalla sin recorrer todo el encuadre). Se ajusta con `GANANCIA_PUNTERO`
(velocidad base) y `ACELERACION` (empuje extra en gestos rápidos).

El movimiento se inyecta con `SendInput` en coordenadas absolutas del escritorio
virtual, así que funciona bien con varios monitores y con escalado de pantalla
(el proceso se declara *DPI-aware*). Sobre la imagen de la cámara se dibujan la
diana y la estela como referencia.

> **Nota:** una versión anterior dibujaba un puntero propio en una ventana
> transparente que cubría todo el escritorio. Daba problemas (se veía como una
> capa opaca que "apagaba" la pantalla), así que se eliminó por completo: ahora
> se mueve directamente el cursor del sistema.

## Los clics

- **Clic izquierdo** → estira **2 dedos** (índice + medio). Un toque corto es un
  clic; si los **mantienes arriba y mueves la mano, arrastras** (arrastrar y
  soltar, seleccionar texto, mover ventanas).
- **Clic derecho** → estira **3 dedos** (índice + medio + anular).

Antes esto se hacía con una pinza (juntar pulgar e índice) y con dos dedos
*pegados* frente a *separados*. Ambos dependían de umbrales de distancia entre
puntas: difíciles de acertar y frágiles. Contar dedos es mucho más fiable, y de
paso desaparecieron todos esos umbrales del código.

Dos detalles para que no falle:

**El clic no arrastra el cursor sin querer.** Al pulsar, el cursor se **congela**
en el sitio, así que el clic cae justo donde apuntabas. Solo cuando mueves la
mano más de `UMBRAL_ARRASTRE` (16 px) pasa a arrastrar de verdad.

**No hay clics accidentales al abrir o cerrar la mano.** Al pasar de puño a mano
abierta los dedos cruzan un instante por "2" y por "3". Contra eso hay dos
defensas: el voto mayoritario de 5 frames (un estado que dura 2 frames no llega
a registrarse) y, para el clic derecho, `ESTABILIDAD_CLIC_DER` (0,15 s) de gesto
mantenido.

**Seguridad:** el botón nunca se queda hundido. Se suelta al perder la mano, al
apagar el control, al cambiar de gesto y al salir del programa (`soltar_todo`).

## El zoom (abrir / cerrar la mano)

- **Mano abierta** (palma, cinco dedos) → **acercar**.
- **Puño** (mano cerrada) → **alejar**.

Mientras mantienes el gesto se van enviando pulsaciones `Ctrl` + `+` / `Ctrl` +
`-` a la **ventana que tengas seleccionada** (la de primer plano): un clic al
empezar y luego uno cada `ZOOM_INTERVALO` segundos. Pasar de palma a puño
invierte el sentido al instante. Es el atajo de zoom más universal de Windows:
navegadores, VS Code, Office, visores de PDF, Explorador...

Detalle importante: como el zoom va a la ventana en primer plano, **la ventana
de la cámara no puede ser la seleccionada** cuando haces el gesto. Si lo es, el
programa lo detecta y no envía nada (silenciosamente). Pincha en la aplicación
que quieras ampliar y sigue gobernándolo todo con la mano.

Si alguna aplicación no responde, pon `ZOOM_NUMERICO = True` para usar el `+`/`-`
del teclado numérico.

## Ajustes de rendimiento

Todo está agrupado en el bloque *Configuración* al inicio de
[gestos_manos.py](gestos_manos.py):

- `ESCALA_DETECCION` (0.6) — la inferencia corre sobre una copia reducida del
  frame; bajarlo a 0.5 va más fluido, subirlo a 1.0 mejora manos lejanas.
- `MAX_MANOS` — ponlo a `1` si solo necesitas una mano: es la mejora de
  fluidez más directa.
- `ANCHO`/`ALTO` — 960×540 es un buen equilibrio; 1280×720 se ve mejor pero
  cuesta en dibujado.
- `GANANCIA_PUNTERO`, `ACELERACION` — velocidad y aceleración del puntero.
- `UMBRAL_ARRASTRE` — cuánto hay que mover la mano para pasar de clic a
  arrastre. `ESTABILIDAD_CLIC_DER` — cuánto hay que mantener los 3 dedos.
- `VENTANA_SUAVIZADO` — frames del voto mayoritario; subirlo da gestos más
  estables (menos clics accidentales) a costa de algo de retraso.
- `ZOOM_INTERVALO` — cadencia del zoom mientras mantienes la mano abierta o
  cerrada (más bajo = zoom más rápido).
- `ESPERA_CONTROL`, `ESPERA_SALIR` — cuánto hay que mantener 👍 y 🤙.
- `SIMULAR_ENTRADA = True` — modo seguro: imprime las acciones en vez de
  enviarlas al sistema.

Otras optimizaciones ya aplicadas: backend DirectShow (arranque rápido en
Windows), `CAP_PROP_BUFFERSIZE=1` para no acumular latencia, modo `VIDEO` del
HandLandmarker (reusa el *tracking* entre frames en vez de redetectar) y
esqueleto dibujado con primitivas de OpenCV. Al quitar todo el texto en pantalla
también se ahorra el dibujado del panel y sus mezclas de transparencia.

## Cómo se clasifica

`dedos_extendidos()` decide dedo a dedo con criterios **angulares** (ángulo de la
articulación PIP, y de la IP para el pulgar) más una comprobación de distancia
respecto a la muñeca. Al no depender de coordenadas absolutas, funciona con la
mano girada o inclinada y a cualquier distancia de la cámara.

`clasificar_gesto()` es luego una simple consulta a la tabla `PATRONES`, que
traduce la tupla `(pulgar, índice, medio, anular, meñique)` a un gesto. Todo el
mapa de gestos cabe de un vistazo y no hay ni un umbral de distancia entre
puntas. El único caso especial es 👍, que además exige que el pulgar apunte
hacia arriba de verdad.

`SuavizadorGesto` aplica un voto mayoritario sobre los últimos 5 frames para que
el gesto no parpadee (y para que los estados intermedios al abrir o cerrar la
mano no cuenten), y `AccionSostenida` exige mantener el gesto y soltarlo antes
de repetir, para que un gesto largo no encadene disparos.

## Qué se ha verificado

Con pruebas automáticas, sin cámara:

- Construcción del `HandLandmarker` y `detect_for_video` con el modelo real
  (también empaquetado en el `.exe`, vía `--selftest`).
- Los 10 patrones de dedos con landmarks sintéticos: cada número de dedos da el
  gesto correcto, no hay patrones duplicados y ningún gesto de clic acaba
  disparando zoom.
- Que **no queda ninguna indicación en pantalla**: ni una llamada a
  `cv2.putText`, ni contador de FPS, y las funciones de panel, etiqueta y barra
  de progreso están eliminadas (el dibujo del esqueleto y la diana se mantienen).
- Air-mouse relativo: arranca anclado al cursor real, la mano lo empuja en la
  dirección correcta, el embrague no salta al recolocar, la zona muerta ignora el
  temblor y nunca se sale del escritorio virtual (incluido un segundo monitor con
  coordenadas negativas).
- Zoom por abrir/cerrar la mano: primer clic inmediato, cadencia mientras se
  mantiene, inversión instantánea palma↔puño y corte al soltar.
- **Clics**: 2 dedos pulsan y sueltan el botón; un temblor pequeño sigue siendo
  clic y un movimiento claro pasa a arrastre; el cursor se congela durante el
  clic; el clic derecho pulsa y suelta sin quedarse abajo y no se dispara al
  cerrar la mano.
- **Seguridad del botón**: `soltar_todo()` libera ambos botones, y cambiar de
  gesto (p. ej. de 2 dedos a mano abierta) lo suelta — nunca queda hundido.
- `AccionSostenida`: progreso, disparo único y rearme tras soltar.
- **Movimiento real del cursor**: `mover_cursor` coloca el cursor de Windows en
  el punto pedido (llamada real a `SendInput`, verificada con `GetCursorPos` y
  devolviendo luego el cursor a su sitio).
- El dispatch del bucle: apuntar mueve el cursor, mano abierta/puño hacen zoom,
  y con el control apagado no se mueve nada.
- `sizeof(INPUT)` correcto en 64 bits.

Sin cámara, **87 comprobaciones en verde** (38 gestos/clics + 32 puntero/zoom
+ 9 dispatch + 8 patrones). Sin probar: la webcam en vivo y el efecto real del
zoom y los clics sobre una aplicación concreta. Eso hay que ejecutarlo delante
de la cámara.
