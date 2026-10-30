# stats.json — fuente unica de numeros de OceanEye Sentinel 2.0

`frontend/data/stats.json` es la unica fuente de cada numero que muestran la landing, el panel Meta de la app, la Arena y el pitch. Ningun numero se escribe a mano en el HTML: cada valor trae `value`, `unit`, `display.es/en`, `n`, `source_path` (ruta JSON del artefacto `$.`, `code:archivo:linea`, `stats:`, `doc:` o `file:sam_masks.json#$.ruta`), `formula` y, si aplica, `caveat` y `ci95`.

Estos archivos son la especificacion. La escena es sintetica (semilla 1982, verdad terreno inyectada) y todo resultado es **indicativo** (n=12 dossiers, n=30 casos, una sola corrida).

| Archivo | Que es |
|---|---|
| `stats.schema.json` | JSON Schema 2020-12. `additionalProperties: false`, unidades cerradas, textos obligatorios (`caveat` cuando n es chico), 12 `forbidden_claims` requeridos. |
| `build_stats.py` | Generador, solo stdlib. Calcula Fisher y McNemar exactos, Wilson 95%, mediana, p90, tokens, costo y 44 chequeos de integridad. |
| `stats.example.json` | Salida real del generador sobre `backend/ml/meta_muse_sam31_benchmark_2026.json` (sha256 en `provenance.artifact`), validada contra el schema. |

## 1. Donde lo pone Hermes

- `scripts/build_stats.py` en el repo (es el nombre que figura en `provenance.generator.script`), junto a los scripts que producen el artefacto.
- `stats.schema.json` al lado del script (o `--schema <ruta>`).
- Se corre despues de cada corrida del benchmark y escribe `frontend/data/stats.json` (donde ya vive la copia del artefacto, `frontend/data/meta_muse_sam31_benchmark_2026.json`). Se versiona. No se edita a mano.
- El repo publica tres espejos identicos de las paginas (`index.html`, `docs/index.html`, `frontend/index.html` comparten sha256; igual `app/index.html`, `docs/app/index.html`, `frontend/app/index.html`), por lo que los numeros de linea de este documento valen para los tres. Copiar `stats.json` byte a byte a `docs/data/stats.json` (lo que sirve GitHub Pages) y a `data/stats.json` para que cada espejo encuentre su `data/` vecino. La misma regla vale para `arena_replay.json`, `sam_masks.json` y `sam_chips/`. Hoy `docs/data` y `frontend/data` traen el artefacto del benchmark y el `data/` de la raiz no; `app/index.html`, `docs/app/index.html` y `frontend/app/index.html` son identicos (sha256 `2a616694…f16f384`).
- Lectura desde el navegador: solo rutas relativas. Desde `app/` usar `fetch('../data/stats.json')` (la misma regla de `arena_replay.json` y `sam_masks.json`); un segundo intento `./data/stats.json`, como hace hoy el cargador del benchmark (`docs/app/index.html` linea 2935), es opcional e inofensivo, pero da 404 porque `app/` solo tiene `index.html`. Desde la landing, `./data/stats.json`. No usar `/data/stats.json`: bajo un subdirectorio como `/OceanEye-hackaton-meta/app/` la ruta absoluta apunta fuera del sitio. La app debe abrirse con la barra final (`/app/`), o `../` sube un nivel de mas.
- Renderizado: poner `display.es|en`, `caveat` y `caveat_en` con `textContent`, nunca con `innerHTML` (los textos llevan `<`, `>`, URLs y nombres de archivo). Nunca mostrar `forbidden_claims[].pattern`.

```
python3 -I scripts/build_stats.py \
  backend/ml/meta_muse_sam31_benchmark_2026.json frontend/data/stats.json \
  --repo-root . --source-commit "$(git rev-parse HEAD)" --require-jsonschema
```

- `--generated-at <ISO>`: pasar el valor anterior da una reconstruccion byte a byte reproducible.
- `--repo-root`: verifica la semilla declarada (1982) contra `backend/app/ingestion/sentinel_fixtures.py` y los conteos declarados `scene.ground_truth_targets` (15) y `scene.dark_targets` (12) contra `backend/tests/fixtures/fixture_metadata.json` (L17-18; 12 = `has_active_ais` falso = `summary_metrics.total_dark_vessels_evaluated`). Sin `--repo-root` esos tres chequeos quedan `ok: null` (no verificados), no cuentan como inconsistencia.
- `--sam-masks <sam_masks.json>`: rellena `sam.real_sar_inspector` solo si `run.mode` es `live` y todos los chips estan `measured`; en cualquier otro caso (`template`, `dry_run`, chips pendientes o con error) queda `not_run` y lo avisa por stderr. Es la unica forma de que se abra el beat B4 del pitch (`statsGate`).
- `--site-packages <dir>`: `-I` ignora el site de usuario; si `jsonschema` esta ahi, hay que indicarlo. `--require-jsonschema` falla si no se puede validar (usarlo en CI; sin la libreria el schema no se aplica).
- Codigos de salida: `0` ok · `1` schema invalido · `2` falla de integridad bloqueante · `3` afirmacion prohibida en el texto generado · `4` entrada invalida. El archivo de salida solo se escribe con `0`.

## 2. `check_integrity.py`

1. **Recalcular y comparar.** Correr el generador sobre el artefacto con el mismo `--generated-at` y comparar con `frontend/data/stats.json` clave por clave; cualquier diferencia falla. Los espejos `docs/data/stats.json` y `data/stats.json` deben ser identicos byte a byte. `provenance.artifact.sha256` debe coincidir con el sha256 real del artefacto en disco.
2. **Integridad.** Falla si `integrity.blocking_failures != 0`. `integrity.known_inconsistencies` (hoy 3) no bloquea pero se imprime siempre: dos literales post-validador del script de evaluacion y el conteo de requests (resumen 83 vs ledger 23 + comparacion 60).
3. **Afirmaciones prohibidas.** Para cada entrada de `forbidden_claims` (regex de Python `re`, no `grep -E`): buscar en los archivos que cubre `applies_to` (`frontend/**/*.html|js|json`) y en todos los textos de `stats.json`, **excluyendo el subarbol `forbidden_claims`** (los patrones y sus `reason` contienen las frases que prohiben y se detectarian a si mismos; el generador hace lo mismo). `severity: error` falla el check; `warn` solo informa. Salida esperada: archivo:linea:id.
4. **Referencias.** Todo `stats:<ruta>` y todo `$.<ruta>` de `source_path` debe resolver. Los `file:sam_masks.json#$.<ruta>` resuelven contra `docs/data/sam_masks.json`; mientras ese archivo no exista (o sea `template`) y `sam.real_sar_inspector.status` sea `not_run`, esas rutas son una excepcion declarada. Tambien debe cumplirse que `docs/data`, `frontend/data` y `data` tengan copias identicas de `stats.json`, `arena_replay.json`, `sam_masks.json` y `sam_chips/*`.

Estado actual del frontend contra los patrones (lo que hoy fallaria): `fc-100-adherence` app 1750 · `fc-100-s30-casos` landing 957/965/1607, app 3451 · `fc-exactitud-reglas-100` landing 1607, app 3451 · `fc-zero-hallucination` landing 957/965/1078/1608, app 1750/3452 · `fc-alucinacion-certificada-label` landing 999/1000/1608, app 3452 · `fc-counter-literals` landing 990/997/1396/1397 · `fc-hallucination-label-from-deficit` app 1750/3022 · `fc-real-satellite-telemetry` landing 1114 · `fc-official-judicial-document` landing 865/1121/1125/1426/1459/1532/1588/1611/1618, app 1353/1361/1362/1443/1561/1562/1807/1808/1864/1866/3249/3283/3369/3430/3455/3462/3527 · `fc-sam-rectangle-as-mask` (warn) app 1704/1736/2979/3002.

## 3. Que elemento lee que clave

Rutas relativas a la raiz de `stats.json`; mostrar `display.<idioma>` y el `caveat` cuando exista.

| Elemento | Claves |
|---|---|
| Landing: marquesina (L957/965) y contadores (L990/997) | `comparison.models.muse_wonder_1_0.raw_valid_count`, `comparison.tests.*`, `dossiers.valid`, `dossiers.flagged_count` |
| Landing: aviso de escena (L1114) | `scene.disclosure`, `scene.badge` |
| Landing y app: PDF / resumen (L1607-1608, app 3451-3452) | `comparison.models.*` (`raw_valid_rate_percent` + `ci95`, `raw_mean_adherence_percent`, `latency_*`, `cost_usd.*`), `comparison.tests.mcnemar_exact_two_sided`, `comparison.tests.fisher_exact_two_sided`, `comparison.indicative_label` |
| App: insignia de adherencia (L1750, L3022) | `dossiers.items[]` por `target_id` → `adherence_percent`, `is_valid`; sin `?? 100.0` ni etiqueta de alucinacion; ver `dossiers.known_issues` |
| App: panel Meta `sumBadge` (L3001-3002) | `api_usage.requests.documented_calls_excluding_uploads` (97), `api_usage.tokens.total`, `api_usage.cost_usd_estimate.total` |
| App: tabla de costos | `pricing.models`, `api_usage.cost_usd_estimate.*`, `comparison.models.*.cost_usd.*` |
| App: Arena (comparador Wonder vs Spark) | `comparison.models.*`, `comparison.tests.paired_table`, `comparison.ratios`, `comparison.cases[]` |
| App: lienzo SAM (L1704, L1736, L2979, L3002) | `sam.disclosure`, `sam.input_kind`, `sam.masks_decodable_from_artifact`, `sam.segmentation_latency_*`, `sam.real_sar_inspector.status` |
| App: insignia de escena | `scene.badge`, `scene.synthetic`, `scene.seed`, `scene.ground_truth_targets`, `scene.dark_targets` |
| App: SAM Mask Inspector (`sam_masks.json`) | `sam.real_sar_inspector.status`, `.input_kind`, `.results.*` (se llenan con `--sam-masks`); las mascaras y cajas se leen de `sam_masks.json`, no de `stats.json` |
| Pitch Mode (`pitch_steps.example.js`, `{ruta\|formato}`) | `scene.synthetic`, `scene.seed`, `scene.badge`, `scene.ground_truth_targets`, `scene.dark_targets`, `comparison.scenarios`, `comparison.runs`, `comparison.models.{muse_wonder_1_0,muse_spark_1_3}.{raw_valid_count,raw_mean_adherence_percent,latency_mean_ms}`, `comparison.ratios.cost_wonder_over_spark`, `sam.real_sar_inspector.status` (compuerta) |
| README del repo | los mismos `display.*` de `comparison`, `dossiers`, `api_usage`; nunca recalcular a mano |

## 4. Literales a reemplazar

- `frontend/app/index.html` ~1750: la insignia hace fallback a `100.0` y rotula "alucinacion" desde el deficit de adherencia. Leer `adherence_percent` de `dossiers.items[target_id]`; si falta el dato, mostrar "sin dato", nunca 100.
- `frontend/app/index.html` ~3451-3452 (PDF): "100%" y "0.00%" fijos. Leer `comparison.*` (tasa valida con IC y mediana de adherencia) y `dossiers.*`. Hoy `0.00%` no tiene ninguna clave que lo respalde.
- `post_validator_adherence_percent = 100.0` en `run_meta_full_evaluation_suite.py` (L174, L180) es un literal del script, no una medicion: el generador lo registra como inconsistencia conocida y no lo usa.

## 5. Reglas de honestidad que impone el schema

- Escena sintetica: `scene.synthetic` es `true` y el texto nunca dice "telemetria satelital real".
- Los 12 registros SAM no son detecciones sobre imagen SAR: `sam.input_kind.value = "illustrative_generated_image"` (imagen de `muse-image-1.0` segmentada con el prompt "ship"); las mascaras guardadas estan truncadas y no se pueden decodificar (0/12).
- El caso real SAR (`sam.real_sar_inspector`) queda `not_run`, con `input_kind.value = "not_applicable"` y `results: null`, hasta que exista un `sam_masks.json` con `run.mode = "live"` y todos los chips `measured` (generador con `--sam-masks`). Los resultados son indicativos (pocos chips).
- Cuando exista esa corrida (docs de SAM): las mascaras son `H,W,~<base85>` sin perdida y `!` marca `one_bit` (https://dev.meta.ai/docs/sam/reading-segmentation); `metadata.include_confidence` se envia como la cadena `"true"`, no como booleano, y los prompts de caja y punto van en la misma parte `input_text` (https://dev.meta.ai/docs/sam/segmenting). Las cajas `<|box;x1;y1;x2;y2;w;h|>` estan en pixeles de origen y `x2`/`y2` son inclusivos (https://dev.meta.ai/docs/sam/segmenting, leida el 2026-10-29); las mascaras de caja y punto siempre vuelven `one_bit`.
- `dossiers.valid` es 11/12 por un falso positivo sospechado del validador (el id de escena "1SDV" se lee como latitud 1 S, SAR-TGT-010). El 12/12 solo va como nota al pie (`valid_if_suspected_false_positives_removed`).
- Wonder vs Spark: McNemar exacto p = 0,0391 (n=30 pares) y Fisher exacto p = 0,0716; son indicativos, sin la palabra "significativo". Wilson 95% acompaña a cada tasa.
- `served_model_verifiable` es `false`: el campo `model` del artefacto guarda el modelo pedido, no el servido.
- Costos son estimaciones con precios de https://dev.meta.ai/docs/pricing-rate-limits (leidos el 2026-10-29); los tokens de razonamiento son un subconjunto de `completion_tokens` y se cobran como salida.
- Un documento generado es un borrador tecnico de apoyo a la decision, simulado; ninguna etiqueta debe sugerir un documento oficial o judicial (`fc-official-judicial-document`, app L3249).
