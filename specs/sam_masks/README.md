# sam_masks.json: contrato de datos del Mask Inspector (Feature #1 de OceanEye Sentinel 2.0)

Destino: `docs/data/sam_masks.json`, con los PNG en `docs/data/sam_chips/` (lo que sirve GitHub Pages). Copiar byte a byte a `frontend/data/` y a `data/` de la raiz, igual que `stats.json` (`specs/stats/README.md`); el snapshot no trae script de sincronizacion, se copia a mano y se comprueba con `cmp`. Estos cuatro archivos son la especificacion; no hay datos medidos todavia.

Vocabulario compartido con el pitch y con `stats.json`: "escena sintetica" / "benchmark sintetico" (los chips de `synthetic_fixture` llevan el rotulo SINTETICO), "indicativo" (pocos chips, una corrida), "imagen ilustrativa" para las 12 mascaras viejas, "REPLAY" solo en el arena. Nunca "telemetria satelital real", "deteccion sobre SAR" para las 12 mascaras viejas, ni lenguaje de documento oficial o judicial.

| Archivo | Para que |
|---|---|
| `sam_masks.schema.json` | JSON Schema 2020-12. Estructura, enums, patrones y reglas por estado. |
| `decode_mask.py` | Solo stdlib. Decodificador de mascaras, trazador de poligonos, IoU, largo por PCA y `--verify` (recalcula todo lo derivado). |
| `sam_masks.example.json` | 1 chip fixture (SAR-TGT-001 = GT-TGT-04), 1 control negativo (fantasma AIS en 300,300), 1 ilustracion legacy. Valida contra el schema. |
| `README.md` | Este archivo. |

El ejemplo es una plantilla: `run.mode = "template"`, `generated_at = null`, los dos chips en `status = "pending"` y cada dato aun no medido es `null` y esta listado en `placeholder_fields`. Los unicos numeros reales son la geometria exacta del fixture y los valores de SAR-TGT-001 copiados del benchmark viejo.

## Dos correcciones al enunciado

1. Las mascaras de caja y de punto no son `~` (lossless). Con prompt de caja o punto la API devuelve siempre `one_bit` (marcador `!`). El prompt de texto/concepto devuelve `~` por defecto; las 12 mascaras viejas son `~` porque eran prompt de texto y el codigo viejo ademas pidio `mask_encoding: lossless`. El campo se llama `mask.encoding` (`one_bit` o `lossless`); la etiqueta vieja `lossless_rle` queda solo en el bloque legacy.
2. El parser viejo (regex) deja de ver las mascaras apenas aparece `;c=`. Con `include_confidence` hay que usar `parse_sam_text` / `parse_sse` de `decode_mask.py` (por clave, no por posicion).

## Pipeline para Hermes

Los pasos 1 a 4 son locales y no gastan nada.

1. CFAR con bbox. `SarVesselDetection` hoy no trae bbox: agregar `r_min/c_min/r_max/c_max` de la componente conectada (campo `cfar.bbox_native_px`).
2. Chip. Ventana de 64x64 pixeles nativos centrada en la deteccion, escalada x8 con vecino mas cercano a 512x512, normalizada en dB con recorte por percentiles 1 y 99.5, PNG de 8 bits en `docs/data/sam_chips/<chip_id>.png`. Guardar `sha256` y los `low/high` realmente aplicados.
3. Prompt. Caja = bbox CFAR + 1 px de margen, en pixeles del chip, extremos inclusivos, maximo 16 objetos. `build_box_prompt` arma el `input_text`. Control negativo: ventana de mar vacio con prompt de texto `ship`.
4. Dry run. `run.mode = "dry_run"`: imprimir el request (sin imagen), el costo estimado y validar el JSON contra el schema. No se llama a la API.
5. Pausa: la llamada paga necesita el "si" explicito de Gaston.
6. Llamada. Subir el chip. El camino probado en el codigo viejo es JPEG por `/v1/files` con `file_id`. La documentacion (segmenting.md) publica `image_url` con URL publica o data URL base64 (ejemplos PNG y JPG) y documenta `file_id` solo para video: PNG por `file_id` sigue sin verificar y `POST https://api.meta.ai/v1/responses` con `stream: true` y `metadata: {"include_confidence": "true"}` (string, no booleano). Guardar el `mask.raw` completo, nunca truncado, y el hash del texto de salida.
7. Decodificar con `meta-sam-parser` (`decode_mask_to_raster`, PyPI 0.1.0, instalarlo necesita aprobacion) y con `decode_mask.py`. Si difieren en una sola mascara, `parsing.rasters_disagreeing > 0` y no se publica.
8. Derivar: `mask_to_polygons(raster, h, w, offset=(x1, y1))`, area, centroide, IoU contra el GT (solo fixture) y largo desde la mascara contra el largo CFAR.
9. Escribir `docs/data/sam_masks.json`, validarlo contra el schema y correr `python3 -I decode_mask.py --verify docs/data/sam_masks.json`.

Colocacion de la mascara: `x` e `y` del tag siempre son 0 y la mascara comparte los limites de la caja (protocol/sam3.md), pero la documentacion no dice que H,W igualen el tamano de la caja. En 11 de las 12 mascaras viejas si (pixel fila r, columna c = pixel del chip (x1 + c, y1 + r), `mask.covers = inclusive_response_bbox`). En SAR-TGT-007 no: mascara 188x1024 contra caja inclusiva 189x1027. Cuando H,W difiere, `mask.covers = dimension_mismatch_VERIFY`: sin poligonos, sin centroide, IoU y largo en `null`, y el visor dibuja solo la caja. `--verify` lo muestra como WARNING, no como error, y marca PROBLEM si el archivo declara `inclusive_response_bbox` con tamanos distintos (o al reves).

## Cambios en `drawMetaSam31Canvas` (`frontend/app/index.html:2948-2993`)

Hoy dibuja la imagen de muse-image-1.0 y un rectangulo relleno rotulado "SAM-3.1 MASK" (usa `x2 - x1`, o sea un pixel menos que el inclusivo). Eso no es una mascara y no es SAR.

- Leer `sam_masks.json` en lugar de `meta_muse_sam31_benchmark_2026.json`; el canvas de 340x210 pasa a respetar el aspecto cuadrado del chip.
- Fondo: `display_image.path` (relativo a `docs/data/`). Escala = `canvas.width / geometry.width`.
- Mascara: todos los `decoded.polygons` de una detection en un solo path con `fill('evenodd')`, escalados por esa misma escala. Nada de `fillRect`.
- Slider de confianza: filtra por `score` en el cliente. `score = null` queda visible con la marca "sin confianza" (un `c` ausente no es 0).
- Mostrar `bbox`, `score`, `metrics.iou_vs_ground_truth.value` y `length_vs_cfar` (mascara vs CFAR). El GT va como contorno punteado y solo existe en chips `synthetic_fixture`; esos chips llevan el rotulo SINTETICO visible.
- Control negativo: mostrar "0 detecciones, control superado" o el fallo tal cual (`control.passed`). Un fallo se muestra como fallo.
- `illustrative_images`: dibujar aparte, sin recuadro, con el rotulo obligatorio "Imagen ilustrativa generada por muse-image-1.0 — no es una detección sobre SAR".
- `runLiveMetaPipelineForCurrentTarget` hoy llama a `/reconstruct-and-segment` (regenera una imagen de muse) y, si falla, muestra igual un "artefacto pre-certificado" con un toast de exito. Quitar ese fallback silencioso; la pagina lee el JSON publicado y no llama a la API desde el navegador.
- Todo texto que venga del JSON (`title`, `name`, `label`, `prompt`, `provenance`, `raw`) se inserta con `textContent` o se dibuja en el canvas con `fillText`, nunca con `innerHTML`; el JSON se trata como dato no confiable.
- Carga: `fetch('../data/sam_masks.json')` y `../data/sam_chips/<chip_id>.png` desde `/OceanEye-hackaton-meta/app/` (con la barra final), la misma regla que `stats.json` y `arena_replay.json`; nunca `/data/...` ni `./data/...`. Hermes confirma en consola que no haya 404. Si el fetch o el parseo fallan, mensaje visible y el resto de la app sigue.

## Pitch Mode (beat B4 de `specs/pitch/pitch_90s.md`) y mapeo a `stats.json`

- Contenedor `#samInspector`. El beat B4 usa el inspector solo si el elemento existe y `sam.real_sar_inspector.status` vale `completed` en `stats.json`; si no, el pitch cae al texto de fallback (SAM segmenta imagenes ilustrativas, no pixeles de radar) y no afirma nada del inspector.
- Evento `pitch:sam` (CustomEvent sobre `document`) con `detail.phase = 'select'`: el inspector elige el primer chip de blanco (`control.is_negative_control = false`) con `status = measured`, dibuja su mascara y su caja, y muestra el rotulo SINTETICO. Sin IoU hablado: el pitch no dice cifras de SAM; las que muestre la pantalla salen del JSON y son "indicativo".
- `status` en `stats.json` no lo escribe nadie a mano: `python3 -I build_stats.py ... --sam-masks docs/data/sam_masks.json` lo pone en `completed` solo si `run.mode = "live"` y todos los chips son `measured`; con `template`, `dry_run`, un chip `pending` o `api_error` se queda en `not_run`.
- Mapeo cuando `completed` (rutas `file:sam_masks.json#...` de `source_path`): `sam.real_sar_inspector.status` <- `$.run.mode`; `input_kind` <- `$.chips[*].source.kind` (`synthetic_sar_chip` si todos son `synthetic_fixture`); `results.chips_total`, `target_chips`, `negative_controls` <- conteos sobre `$.chips`; `negative_control_detections` <- suma de `control.observed_detections` en los controles negativos; `iou_mean_vs_ground_truth` <- media de `detections[*].metrics.iou_vs_ground_truth.value` en los chips de blanco (indicativo); `latency_mean_ms` <- media de `sam_response.latency_ms`.
- Los 12 registros SAM de `meta_muse_sam31_benchmark_2026.json` siguen siendo `sam.input_kind = illustrative_generated_image` y no cuentan como detecciones sobre SAR.

## Costo (SAM: USD 2.50 cada 1000 imagenes, USD 0.0025 por imagen)

| Chips (1 request cada uno) | USD |
|---|---|
| 2 (el ejemplo) | 0.005 |
| 10 | 0.025 |
| 20 | 0.05 |
| 30 | 0.075 |
| 100 | 0.25 |
| 1000 | 2.50 |

Cada reintento es otra imagen facturada (`run.cost.billed_images`). Si un request con varias cajas se factura una vez o por objeto no esta confirmado: queda `multi_object_billing = "unknown_VERIFY"` hasta el primer run. Limite publicado: 3,000 RPM. Muse-image-1.0 ($0.01 por imagen, precio de lista de la pagina de precios; el benchmark viejo no registra ningun precio) deja de usarse en este flujo.

## Las 12 mascaras actuales no se pueden decodificar

`backend/ml/meta_muse_sam31_benchmark_2026.json` guarda de cada mascara solo `rle_preview`: 120 caracteres mas `...`, de un total de 6,183 a 62,234 caracteres. Las 12 son `~`, prompt de texto `ship`, sobre una imagen generada por muse-image-1.0. Ademas la vista previa embebida es de 512x512 pero SAM corrio sobre una subida de 1600x1600 que no se guardo. Quedan como `illustrative_images` (`decodable: false`) y no cuentan como detecciones. Hace falta un run nuevo con el string completo.

## Cosas que no cierran y quedan expuestas

- Espaciado del fixture: el generador dice 10 m, pero los grados por pixel de sus bounds implican unos 157 x 223 m. El JSON guarda ambos (`pixel_spacing_m` con `pixel_spacing_basis`, y `geotransform_implied_spacing_m`, `spacing_consistent_with_geotransform = false`). Hay que elegir uno antes de publicar metros; no mezclar.
- El vessel GT-TGT-04 mide 7 pixeles nativos de largo y 1 de ancho. SAM puede no segmentarlo. Ese resultado se reporta tal cual, no se asume exito.
- El slider solo filtra lo que la API ya devolvio; no hay parametro de umbral documentado (VERIFY).

## VERIFY (no documentado o no confirmado)

Internos del codec aritmetico (conteos, halving, predictor lossless); `meta-sam-parser` manda. El vector one_bit 5x5 del protocolo no trae raster publicado: solo prueba que decodifica y se re-codifica al mismo payload. Relacion entre H,W de la mascara y la caja (ver Colocacion). Sintaxis exacta del token de punto con etiqueta. Si la API reescala imagenes grandes y repite `w/h` (`meta_muse_engine.py` pide 1024x1024 a muse, pero las cajas del benchmark viejo reportan w/h 1600x1600; no se sabe si fue un reescalado). PNG por `file_id` como transporte. Donde viene el id del modelo servido en la respuesta (`response.model` es supuesto). Facturacion de varios objetos por request.

## Fuentes

- https://dev.meta.ai/docs/sam/reading-segmentation
- https://dev.meta.ai/docs/sam/segmenting.md (caja y punto siempre one_bit, `include_confidence` como string, hasta 16 objetos, x2/y2 inclusivos, `image_url`; releida el 2026-10-29)
- https://github.com/meta-models/meta-sam/blob/main/protocol/sam3.md
- https://github.com/meta-models/meta-sam/tree/main/conformance/cases (vectores oficiales usados en `--selftest`)
- https://dev.meta.ai/docs/pricing-rate-limits (leida el 2026-10-29)
