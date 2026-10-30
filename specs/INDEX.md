# OceanEye Sentinel 2.0: índice de las specs

Meta Global AI Developer Hackathon, cierre el 4 de noviembre de 2026 a las 21:00 (ET). Estado al 2026-10-29: todo lo de acá es especificación y datos derivados del artefacto `backend/ml/meta_muse_sam31_benchmark_2026.json` (sha256 `011a7510af5b...` en `provenance.artifact`, snapshot del repo en `cd56a3f`, el artefacto entró en `b31d4ba`). No se llamó a ninguna API de Meta y no se gastó dinero.

La escena es sintética (semilla 1982, verdad terreno inyectada) y todo resultado es indicativo (n = 12 dossiers, n = 30 casos, una sola corrida). Los modelos son `muse-wonder-1.0`, `muse-spark-1.3`, `muse-image-1.0` y `sam-3.1`.

## 1. Qué es cada archivo

### `stats/`: fuente única de números

| Archivo | Qué es |
|---|---|
| `README.md` | Dónde lo pone Hermes, `check_integrity.py` (spec, no existe en el repo), qué elemento lee qué clave, literales a reemplazar, reglas de honestidad. |
| `stats.schema.json` | JSON Schema 2020-12 de `stats.json`. Unidades cerradas, `caveat` obligatorio con n chico, 12 `forbidden_claims` requeridos. |
| `build_stats.py` | Generador (stdlib). Fisher y McNemar exactos, Wilson 95%, costos, 44 chequeos de integridad. Códigos de salida: 0 ok, 1 schema, 2 integridad, 3 afirmación prohibida, 4 entrada inválida. |
| `stats.example.json` | Salida real del generador sobre el artefacto. 44 chequeos, 0 bloqueantes, 3 inconsistencias conocidas. Se reconstruye idéntico byte a byte. |

### `pitch/`: guion de 90 s

| Archivo | Qué es |
|---|---|
| `pitch_90s.md` | 8 beats, 90.0 s, EN y ES. Tabla de claves de `stats.json`, beats condicionales con fallback, restricciones de honestidad, checklist previo a grabar, preguntas abiertas. |
| `pitch_steps.example.js` | Los 8 pasos de Pitch Mode con placeholders `{ruta\|formato}`. Lee `../data/stats.json`; sin el archivo o sin una clave, el beat usa su caption sin números. |

### `arena_replay/`: Wonder vs Spark en REPLAY

| Archivo | Qué es |
|---|---|
| `README.md` | Semántica del replay, estado de los datos v0, cambios para la recaptura v1, arreglos al validador (F1 a F6), costo, Pitch Mode, notas de UI. |
| `arena_replay.schema.json` | JSON Schema 2020-12 (`v0-artifact-derived` y `v1-streamed-capture`). |
| `arena_replay.v0.example.json` | 3 casos (TC-EEZ-001, TC-SKM-010, TC-ADV-029) armados solo con datos de hoy, con timing interpolado. Alcanza para maquetar la UI. |
| `build_arena_v0.py` | Genera el v0 desde el repo. |
| `reference_validator_spans.py` | Validador con spans, en paridad con el heredado (no corrige falsos positivos). |
| `validate_arena.py` | Schema, invariantes y contraste con `rules_engine.py`. |
| `audit_validator_fp.py` | Muestra cada falso positivo del validador heredado en contexto. |

### `sam_masks/`: Mask Inspector sobre chips SAR

| Archivo | Qué es |
|---|---|
| `README.md` | Pipeline para Hermes (9 pasos), cambios al lienzo SAM, Pitch Mode y mapeo a `stats.json`, costo, lo que no cierra, VERIFY. |
| `sam_masks.schema.json` | JSON Schema 2020-12 de `sam_masks.json`. |
| `sam_masks.example.json` | Plantilla con 2 chips pendientes (`fx-mile201-sar-tgt-001-box` y `fx-mile201-ghost-ais-empty-sea`), `run.mode` de plantilla. |
| `decode_mask.py` | Decodificador de máscaras, trazador de polígonos y verificador (stdlib). `--selftest` y `--verify`. |

`pitch/_to_delete/` es basura mía de pruebas (ver sección 6). No usar.

## 2. Contrato compartido (las cuatro carpetas dicen lo mismo)

- Rutas de datos: el generador escribe `frontend/data/<archivo>`; copiar byte a byte a `docs/data/` (lo que sirve GitHub Pages) y a `data/` de la raíz. El snapshot no trae script de sincronización: copiar a mano y comprobar con `cmp`. Vale para `stats.json`, `arena_replay.json`, `sam_masks.json` y `sam_chips/`.
- Carga desde el navegador: relativa, sin barra inicial. Desde `/OceanEye-hackaton-meta/app/` (con la barra final) es `fetch('../data/<archivo>')`. Nunca `/data/...` (apunta a la raíz del dominio). `./data/...` da 404 porque `docs/app/` solo tiene `index.html`.
- Texto de modelo y de `stats.json` siempre con `textContent`, nunca `innerHTML`. No mostrar `forbidden_claims[].pattern`.
- Ids y eventos del pitch: `#samInspector` con `pitch:sam {phase:'select'}`; `#replayArena` con `pitch:arena {phase:'accuracy'|'speed'}`; `#btnVerifyInBrowser` con `pitch:verify {}`; además `#syntheticSceneBadge`, `#metaApiPanel`, `#dossierLayaSigBox`. No hay evento de salida: cada componente corre su propio reloj.
- Vocabulario: REPLAY, indicativo, escena sintética de prueba, escenario de prueba escrito a mano, texto generado por un modelo, borrador técnico de apoyo a la decisión para revisión humana. Nada que sugiera un documento oficial o judicial.
- Precios (https://dev.meta.ai/docs/pricing-rate-limits, leídos el 2026-10-29), por 1 M de tokens: Wonder 4.00 entrada, 0.20 cacheada, 20.00 salida; Spark 1.25, 0.15 y 4.25. `muse-image-1.0` USD 0.01 por imagen. `sam-3.1` USD 2.50 cada 1000 imágenes (0.0025 por imagen). El razonamiento se cobra a la tarifa de salida; el caché se ignora, así que toda estimación es una cota superior.

## 3. Orden de implementación para Hermes

Los pasos 1 a 7 no gastan nada. Los pasos 8 y 9 esperan el "sí" de Gaston a un monto concreto. El paso 10 cierra.

1. **`stats.json`.** Copiar `build_stats.py` y `stats.schema.json` a `scripts/`. Correr:
   `python3 -I scripts/build_stats.py backend/ml/meta_muse_sam31_benchmark_2026.json frontend/data/stats.json --repo-root . --source-commit "$(git rev-parse HEAD)" --require-jsonschema`
   Copiar a `docs/data/` y `data/` y comprobar con `cmp`. Listo cuando sale 0, `integrity.blocking_failures` es 0 y las tres copias son idénticas.
2. **Leer `stats.json` en landing y app, y reemplazar los literales** de la sección 4 del README de stats: `app` ~1750 (fallback 100.0), `app` ~3451-3452 (PDF), `landing` 957/965/990/997/999/1000/1078/1396/1397/1607/1608. Sin esto el checklist del pitch (que greppea el texto renderizado) no pasa.
3. **Arena v0.** Publicar `arena_replay.v0.example.json` (o regenerarlo con `build_arena_v0.py --repo <repo>`) como `docs/data/arena_replay.json` más espejos. Construir `#replayArena`: reloj compartido, REPLAY x8 por defecto, rótulo "timing interpolado", lápiz rojo apagado (`ui_policy.red_pen_enabled = false`) y distancia a la ZEE solo dentro de la tarjeta del escenario, rotulada "Escenario de prueba: valor dado, no medido". Validar con `validate_arena.py --repo <repo> --selftest`.
4. **Pitch Mode.** Pasar `pitch_steps.example.js` al repo con `PITCH_STATS_URL='../data/stats.json'`, los ids y eventos de la sección 2 y los fallbacks de B4, B5, B6 y B7. Probar `?pitch=1&lang=en` y `lang=es` con la consola abierta: ni "missing stats keys" ni 404.
5. **`check_integrity.py`.** Escribirlo según la sección 2 del README de stats (recalcular y comparar, `blocking_failures`, `forbidden_claims`, referencias, espejos con `cmp`) y engancharlo a CI.
6. **Arreglos F1 a F5 del validador** (README de arena), cada uno con test; los 16 falsos positivos son los tests de regresión y deben dar 0 hallazgos. Hasta entonces `validator.status` no puede ser `verified` y 26/19 y 98/92 quedan "indicativos, posiblemente distorsionados".
7. **Pipeline SAM, pasos 1 a 4** (README de SAM): bbox en CFAR, chip PNG, prompt de caja, dry run. Más el Mask Inspector leyendo `sam_masks.json` en modo plantilla. Se detiene antes de la llamada paga. B4 sigue con fallback porque `sam.real_sar_inspector.status` es `not_run`.
8. **Puerta A (OK de Gaston): corrida SAM real** sobre chips, pasos 5 a 9 del README de SAM. Después regenerar `stats.json` con `--sam-masks` y `python3 -I decode_mask.py --verify docs/data/sam_masks.json`.
9. **Puerta B (OK de Gaston): recaptura v1 del arena.** Primero la prueba de humo con TC-EEZ-001 en ambos modelos, después los 30 casos, con tope duro de gasto en el script. Con F1 a F5 en el repo y `validator.status = verified`, se enciende el lápiz rojo.
10. **Cierre.** Regenerar `stats.json` (el pitch dice 26/19, 98/92, 11.7/28.6 y 24 que pueden cambiar), volver a contar palabras, correr el chequeo de render, `check_integrity.py`, `cmp` de espejos, grabar EN y ES por separado a 1920x1080.

## 4. Qué se puede hacer hoy y qué necesita el OK de Gaston

| | Sin gasto (hacer ya) | Necesita el OK de Gaston |
|---|---|---|
| Estadísticas | `stats.json` completo, schema, integridad, textos EN y ES. | |
| Arena | v0 con 3 casos y timing interpolado, UI completa, validador arreglado y probado. | Recaptura v1 en streaming (puerta B). |
| Pitch | Los 8 beats con los condicionales B4 a B7 y sus fallbacks, grabable hoy con datos v0 rotulados. | |
| SAM | Pasos 1 a 4 (bbox, chip, prompt, dry run) y UI en modo plantilla. | Llamadas a `sam-3.1` sobre chips reales (puerta A); instalar `meta-sam-parser` (PyPI 0.1.0), que además pide aprobación aparte. |

Costos que acompañan cada puerta (todos son estimaciones, cota superior):

- **SAM** (USD 0.0025 por imagen, un request por chip): 2 chips = 0.005; 10 = 0.025; 100 = 0.25. Cada reintento es otra imagen facturada. Si un request con varias cajas se factura una vez o por objeto no está confirmado.
- **Arena v1** (30 casos x 2 modelos, una pasada): 1.53 esperado (1.531044), 2.30 con colchón 1.5x, tope duro propuesto 4.00. Máximo teórico sin reintentos si las 60 llamadas llegan a `max_tokens = 4096`: 3.01. Prueba de humo (1 caso, ambos modelos): unos 0.051. El brazo B opcional (prompt con distractores) se aprueba aparte: +1.5 esperado y +3.0 como máximo, más la entrada extra, que no está estimada.
- Mientras no haya OK no se llama a `api.meta.ai`, y el pitch se graba con v0 y el fallback de B4.

Ruta mínima si falta tiempo: pasos 1 a 4 y grabar con los fallbacks. Los pasos 8 y 9 mejoran el pitch pero no lo bloquean.

## 5. Lista VERIFY (no documentado o no confirmado)

Cada ítem figura en el archivo indicado. Ninguno está confirmado en la documentación de Meta (https://dev.meta.ai/docs).

**Datos de escenarios**
1. La distancia de TC-EEZ-001 ("-86.47 NM", dentro de la ZEE) no está contrastada con `data/argentina_eez.geojson` (arena README, notas de UI; pitch, pregunta 7). La línea de ZEE queda apagada en el pitch y Gaston decide qué caso destaca el arena (TC-EEZ-001, o TC-SKM-010 con 0.05 NM, escrito a mano).

**SAM y máscaras** (`sam_masks/README.md`, `sam_masks.schema.json`, `sam_masks.example.json`, `decode_mask.py`)
2. Relación entre H,W de la máscara y el tamaño de la caja: la documentación dice que comparten límites, no que H,W sean iguales. En 11 de las 12 máscaras viejas coinciden; SAR-TGT-007 no (188x1024 contra 189x1027). Esa se declara `mask.covers = dimension_mismatch_VERIFY`, sin polígonos, centroide, IoU ni largo.
3. Facturación de varios objetos en un request: `multi_object_billing = "unknown_VERIFY"` hasta la primera corrida.
4. Umbral de confianza: no hay parámetro documentado; el slider solo filtra lo que la API ya devolvió.
5. Sintaxis exacta del token de punto con etiqueta (`label` positivo o negativo).
6. Si la API reescala imágenes grandes y repite `w/h` (las cajas viejas reportan 1600x1600 y el motor pedía 1024x1024 a muse); campo `w/h` nulo si coinciden con lo subido.
7. PNG por `file_id` como transporte: la documentación publica `image_url` (URL o data URL base64) y documenta `file_id` solo para video.
8. Dónde viene el id del modelo servido en la respuesta de SAM (`response.model` es supuesto; `model_served_source` del schema).
9. Internos del códec aritmético de `decode_mask.py`: mitad del conteo "con mínimo 1" (se asume piso y luego tope), contexto de orden 1 y 2 del modo lossless, constantes del range coder (carry-less, 32 bits), conteos iniciales (1,1) con +14 por bit y mitad al llegar a 4096, y el modelo lossless completo. Manda `meta-sam-parser`; el vector one_bit 5x5 del protocolo no trae raster publicado, solo prueba que decodifica y recodifica al mismo payload.
10. Firma pública de `meta-sam-parser`; la documentación solo nombra la función.
11. Unidades de calibración respecto de la entrada del CFAR (potencia lineal, dB solo para mostrar) y `pixel_spacing_basis = assumed_VERIFY` si no sale del fixture ni de metadatos del producto.

**Recaptura del arena** (`arena_replay/README.md`, `arena_replay.schema.json`)
12. `max_tokens` es alias obsoleto de `max_completion_tokens`: si se renombra, verificar que la semántica sea idéntica (el tope cuenta razonamiento más salida visible). Mantener `max_tokens = 4096` mientras tanto.
13. Nivel por defecto de `reasoning_effort` (no documentado). El suite de hoy no lo envía; tampoco enviarlo en la recaptura (`provenance.reasoning_effort = null`).
14. `stream_options.include_usage` no figura en la documentación. Si no devuelve `usage` en el último chunk, hay que medir latencia en streaming y tokens en una llamada aparte sin streaming.
15. `model` en los chunks SSE (la documentación lo muestra solo sin streaming). Si no viene, la prueba de humo se hace sin streaming y se compara `model`. Si `model_served` difiere de `model_requested`, la corrida se marca y no entra al arena.
16. `reasoning_tokens` en el `usage` final con streaming, y `cached_tokens` en el último chunk SSE.

Los ítems 14 a 16 se confirman con la prueba de humo de TC-EEZ-001 antes de gastar la corrida completa.

## 6. Abiertos sin etiqueta VERIFY y decisiones que son de Gaston

- **Inconsistencias conocidas en `stats.json` (3, no bloquean):** `post_validator_adherence_percent = 100.0` es un literal del script de evaluación (en Wonder y en Spark) y no una medición; el conteo de requests no cierra (resumen 83 contra ledger 23 más comparación 60). El generador las registra y no las usa.
- **Validador heredado:** el id de escena "1SDV" se lee como latitud en SAR-TGT-010 (sospecha de falso positivo en los dossiers) y, en los 240 caracteres guardados de las narrativas, 16 hallazgos de 11 de los 15 resultados marcados son falsos positivos leyendo el contexto (`audit_validator_fp.py`); los otros 4 resultados marcados no se pueden juzgar. Por eso `dossiers.valid` es 11 de 12 y el 12 de 12 va solo como nota al pie; 26/19 y 98/92 se dicen "indicativos".
- **Tolerancia del validador para dB (F4):** 0.5 dB propuesto, decisión pendiente.
- **Texto fijo en la app y la landing** (lista del paso 2): hasta reemplazarlo, `forbidden_claims` falla contra el frontend actual.
- **`#btnVerifyInBrowser` y `pitch:verify` (feature #5) no tienen spec.** B7 usa el fallback `#dossierLayaSigBox` sin verificación en el navegador.
- **Rotar la clave de firma:** el repo trae una semilla Ed25519 por defecto commiteada en `backend/app/laya/custody_gateway.py:36`. B7 dice "clave de demo" sobre esa base. Decidir si se rota antes de grabar. No copiar el valor a ningún documento.
- **Repo público al entregar:** B8 dice "repo público" y la URL de `stats.json`.
- **Spark para triage:** B6 dice "sugiere" y debe seguir así hasta que el ruteo esté implementado.
- **Timing de v0 interpolado:** las latencias medidas son con hasta 8 solicitudes en paralelo y sin alternar modelos (n = 1); a x8, los 28.6 s promedio de Wonder se reproducen en unos 3.6 s. Se rotula "timing interpolado" hasta tener v1.

## 7. Reglas que no se rompen

- Todo número visible sale de una ruta JSON del artefacto con fórmula declarada (`source_path` y `formula` en `stats.json`); nada se escribe a mano.
- Ni la cifra de puntaje completo de adherencia ni el porcentaje de cero alucinaciones aparecen en ninguna pantalla; el schema los prohíbe y el pitch los lista como "no decir".
- Los 12 registros SAM actuales no son detecciones sobre imagen SAR: son imágenes generadas por `muse-image-1.0` segmentadas con el prompt "ship" (`sam.input_kind = illustrative_generated_image`, 0 de 12 decodificables). El caso SAR real solo existe tras la puerta A.
- Ningún texto dice "telemetría satelital real" para la escena sintética, ni sugiere documento oficial o judicial.
- Resultados con n chico se dicen "indicativos": McNemar exacto p = 0,0391 y Fisher exacto p = 0,0716, sin la palabra "significativo".
- Nombre del producto: "OceanEye Sentinel 2.0".

## 8. Cómo comprobar que todo sigue verde

Desde `specs/`, con `PYTHONDONTWRITEBYTECODE=1` para no generar `__pycache__`:

```
python3 -I stats/build_stats.py <artefacto> <salida> --repo-root <repo> --require-jsonschema --site-packages <site-packages del usuario>
python3 -I arena_replay/validate_arena.py --repo <repo> --selftest arena_replay/arena_replay.v0.example.json
python3 -I arena_replay/audit_validator_fp.py --repo <repo>
python3 -I sam_masks/decode_mask.py --selftest
python3 -I sam_masks/decode_mask.py --verify sam_masks/sam_masks.example.json
```

`<site-packages del usuario>` es donde está `jsonschema` (4.26); `-I` ignora el site de usuario, por eso hay que indicarlo. Nada de esto instala paquetes ni llama a la API.
