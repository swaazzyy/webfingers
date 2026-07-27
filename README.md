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

| Gesto | Qué hace |
|:---:|---|
| ☝️ **1 dedo** (índice) | **mueve el cursor** de Windows |
| ✌️ **2 dedos** (índice + medio) | **clic izquierdo** — mantén y mueve para **arrastrar** |
| 👍 **pulgar arriba** | **clic derecho** |
| ✋ **mano abierta** | **acercar** con la Lupa, sostenido |
| ✊ **puño** | **alejar** con la Lupa, sostenido |
| 🤙 **pulgar + meñique** | mantén **1,2 s**: activa/desactiva el control |

**Salir:** tecla `q`/`ESC` o el botón X de la ventana.

Ningún gesto usa el **anular**, ni te obliga a mover el **meñique por separado**
— son los dedos más difíciles de aislar. El pulgar da igual al apuntar y al
hacer clic: `1 dedo` y `1 dedo + pulgar` (la "L") hacen lo mismo. Cualquier otra
forma no hace nada.

## Archivos

- [gestos_manos.py](gestos_manos.py) — detección, clasificación y bucle principal
- [control_windows.py](control_windows.py) — movimiento del cursor y zoom (SendInput)

## Instalación

Funciona en cualquier PC con Windows y Python 3.9–3.13. Desde la carpeta del
proyecto:

```bash
py -m venv .venv && .venv\Scripts\python.exe -m pip install -r requirements.txt
```

Si no tienes Python, instálalo desde [python.org](https://www.python.org/downloads/).
`iniciar.bat` también funciona sin entorno virtual: si no encuentra `.venv`, usa
el Python del sistema.

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

### Calibración portable

La sensibilidad **no está en píxeles**, sino en unidades relativas: el
desplazamiento del dedo se mide como fracción del encuadre y se convierte a
fracción de la pantalla. Por eso `GANANCIA_PUNTERO = 2.0` significa *"cruzar el
encuadre entero equivale a cruzar 2 pantallas"* — y eso vale igual en un
portátil de 1366×768 que en un monitor 4K, y con una webcam de 640×480 o de
1080p.

### Ajustar la sensibilidad

Cambia **solo `GANANCIA_PUNTERO`**. Esta tabla dice qué porcentaje de la pantalla
recorre el cursor según lo que muevas la mano (100 % = llegas al borde):

| `GANANCIA_PUNTERO` | gesto corto<br>(15 % del encuadre) | gesto medio<br>(25 %) | barrido<br>(50 %) |
|:---:|:---:|:---:|:---:|
| 1.0 | 17 % | 30 % | 70 % |
| 1.3 | 23 % | 39 % | 91 % |
| 1.6 | 28 % | 48 % | 100 % |
| **2.0** ← actual | **35 %** | **59 %** | **100 %** |
| 2.5 | 43 % | 74 % | 100 % |
| 3.0 | 52 % | 89 % | 100 % |
| 4.0 | 69 % | 100 % | 100 % |

Si el cursor se te queda corto, sube a 2.5 o 3.0. Si se te escapa y no puedes
afinar, baja a 1.6. Por encima de 3.0 cuesta apuntar a cosas pequeñas.

Antes estaba en píxeles crudos, y eso hacía que la app fuera **disparada en una
pantalla pequeña y lentísima en una 4K**, además de cambiar de tacto según la
resolución de la webcam. Hay un test que barre el dedo un 25 % del encuadre en
4 pantallas y 4 webcams distintas y comprueba que el cursor recorre siempre el
mismo 59 % de la pantalla (dispersión < 0,05 %).

Lo mismo vale para `ZONA_MUERTA` y `UMBRAL_ARRASTRE`: también son fracciones del
encuadre, no píxeles.

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
- **Clic derecho** → **pulgar arriba** 👍. Tiene que apuntar hacia arriba de
  verdad: un puño con el pulgar asomando de lado no cuenta.

Antes el clic derecho eran 3 dedos, pero exigía estirar el **anular** dejando el
meñique abajo — un movimiento que a casi nadie le sale limpio, y el meñique
tiende a subirse solo. El pulgar es independiente por naturaleza, así que sale
sin pensar.

Dos detalles para que no falle:

**El clic no arrastra el cursor sin querer.** Al pulsar, el cursor se **congela**
en el sitio, así que el clic cae justo donde apuntabas. Solo cuando mueves la
mano más de `UMBRAL_ARRASTRE` (16 px) pasa a arrastrar de verdad.

**No hay clics accidentales al abrir o cerrar la mano.** Al pasar de puño a mano
abierta los dedos cruzan un instante por "2" y por "solo pulgar". Contra eso hay
dos defensas: el voto mayoritario de 5 frames (un estado que dura 2 frames no
llega a registrarse) y, para el clic derecho, `ESTABILIDAD_CLIC_DER` (0,15 s) de
gesto mantenido.

**Seguridad:** el botón nunca se queda hundido. Se suelta al perder la mano, al
apagar el control, al cambiar de gesto y al salir del programa (`soltar_todo`).

## El zoom: la Lupa de Windows

- **Mano abierta** ✋ → **acercar**.
- **Puño** ✊ → **alejar**.

Se envía `Win` + `+` / `Win` + `-`, que controla la **Lupa de Windows**: la
función de zoom nativa del sistema. Amplía **toda la pantalla**, así que funciona
en cualquier aplicación, en el escritorio y hasta en los menús — da igual qué
ventana tengas seleccionada.

Antes esto era `Ctrl` + `+`/`-`, el zoom interno de cada app. Tenía dos pegas
que la Lupa elimina: solo funcionaba donde estuviera implementado (nada en el
Escritorio, el menú Inicio o muchas apps), y obligaba a tener esa ventana en
primer plano — lo que chocaba con la propia ventana de la cámara.

Mientras mantienes el gesto se envía un paso al empezar y luego uno cada
`ZOOM_INTERVALO` segundos. Pasar de palma a puño invierte el sentido al instante.

Al cerrar el programa se envía `Win` + `Esc` para **cerrar la Lupa y devolver la
pantalla a su tamaño normal** — pero solo si fuimos nosotros quienes la abrimos,
para no cerrártela si ya la estabas usando por tu cuenta. Se desactiva con
`CERRAR_LUPA_AL_SALIR = False`.

Un detalle de implementación: al pulsar `Win` siempre se pulsa otra tecla antes
de soltarla. Si `Win` se pulsara y soltara sola, Windows abriría el menú Inicio.

## Ajustes de rendimiento

Todo está agrupado en el bloque *Configuración* al inicio de
[gestos_manos.py](gestos_manos.py):

- `ESCALA_DETECCION` (0.6) — la inferencia corre sobre una copia reducida del
  frame; bajarlo a 0.5 va más fluido, subirlo a 1.0 mejora manos lejanas.
- `MAX_MANOS` — ponlo a `1` si solo necesitas una mano: es la mejora de
  fluidez más directa.
- `ANCHO`/`ALTO` — 960×540 es un buen equilibrio; 1280×720 se ve mejor pero
  cuesta en dibujado.
- `GANANCIA_PUNTERO` — sensibilidad del cursor; usa la
  [tabla de arriba](#ajustar-la-sensibilidad). `ACELERACION` — empuje extra en
  los gestos rápidos, para cruzar la pantalla de un manotazo.
- `INDICE_CAMARA` — `None` busca la webcam sola; pon un número para forzar una.
- `UMBRAL_ARRASTRE` — cuánto hay que mover la mano para pasar de clic a
  arrastre. `ESTABILIDAD_CLIC_DER` — cuánto hay que mantener 👍.
- `VENTANA_SUAVIZADO` — frames del voto mayoritario; subirlo da gestos más
  estables (menos clics accidentales) a costa de algo de retraso.
- `ZOOM_INTERVALO` — cadencia del zoom mientras mantienes la mano abierta o
  cerrada (más bajo = zoom más rápido).
- `ESPERA_CONTROL` — cuánto hay que mantener 🤙 para activar/desactivar.
- `CERRAR_LUPA_AL_SALIR` — si al salir se devuelve la pantalla al 100 %.
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
- Zoom por abrir/cerrar la mano: primer paso inmediato, cadencia mientras se
  mantiene, inversión instantánea palma↔puño y corte al soltar.
- **Lupa**: arranca cerrada, acercar la marca como abierta, alejar no la abre,
  y `cerrar_lupa()` es idempotente (no reenvía `Win`+`Esc` de más).
- Que ningún gesto exige estirar el **anular** ni aislar el **meñique**, y que un
  pulgar asomando **de lado** no dispara el clic derecho.
- **Portabilidad**: el mismo gesto recorre el mismo % de pantalla en 1366×768,
  1080p, QHD y 4K, y con webcams de 640×480 a 1080p (dispersión < 0,05 %); el
  cursor no se sale por el borde de un monitor en coordenadas negativas; y
  ningún archivo distribuible contiene rutas absolutas.
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

Sin cámara, **109 comprobaciones en verde** (50 gestos/clics/lupa + 31
puntero/cursor + 12 portabilidad + 9 dispatch + 7 patrones). Sin probar: la
webcam en vivo y el efecto real de la Lupa y los clics sobre una aplicación
concreta. Eso hay que ejecutarlo delante de la cámara.
