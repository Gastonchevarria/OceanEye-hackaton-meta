# Wonder vs Spark Replay Arena: especificación de `docs/data/arena_replay.json`

Feature #2 de OceanEye Sentinel 2.0. Pantalla dividida estática (GitHub Pages): los dos modelos responden el mismo caso, las narrativas se escriben a su velocidad relativa real, comprimidas y rotuladas "REPLAY x8". Cada lado muestra reloj, tokens y costo estimado; el "lápiz rojo" del validador subraya los números mal citados con "esperado X / dijo Y".

Este paquete es solo especificación y datos derivados. No llamó a ninguna API de Meta y no gastó dinero.

Vocabulario compartido con el pitch y con `stats.json`: "REPLAY" (nunca "en vivo"), "indicativo" (n = 1 por caso), "escenario de prueba escrito a mano" (no detecciones), "texto generado por un modelo", "borrador de apoyo a la decisión para revisión humana" (nunca "dictamen", "prueba" ni "evidencia legal"). La escena de la app es un benchmark sintético y no se presenta como telemetría satelital real.

## Archivos

| Archivo | Para qué |
|---|---|
| `arena_replay.schema.json` | JSON Schema 2020-12 del archivo final (`v0-artifact-derived` y `v1-streamed-capture`). |
| `arena_replay.v0.example.json` | 3 casos (TC-EEZ-001, TC-SKM-010, TC-ADV-029) armados solo con datos de hoy. Sirve para maquetar la UI ya. |
| `build_arena_v0.py` | Genera el v0 desde el repo (solo stdlib). Reconstruye los prompts desde el AST del suite. |
| `reference_validator_spans.py` | Referencia del validador con spans, en paridad con el heredado (no corrige falsos positivos). |
| `validate_arena.py` | Valida schema e invariantes (usage, costo, NFC, offsets UTF-16, timeline) y contrasta el veredicto con `rules_engine.py`. |
| `audit_validator_fp.py` | Corre el validador real sobre los datos de hoy y muestra cada hallazgo en contexto. |

```
python3 -I build_arena_v0.py --repo <repo> [--cases TC-EEZ-001,...] [--generated-at ISO]
python3 -I validate_arena.py --repo <repo> --selftest [archivo.json]
python3 -I audit_validator_fp.py --repo <repo>
```

`validate_arena.py` y `audit_validator_fp.py` agregan el site-packages del usuario (jsonschema, pydantic); no instalan nada.

## Semántica del replay

- Un reloj compartido: `t_replay = t_pared × velocidad`, velocidad en `replay.speed_options` (`[1,2,4,8,16]`, por defecto `replay.default_speed` = 8). Cada lado se detiene en su `latency_ms`; el más lento sigue corriendo y se nota.
- Etiqueta fija `replay.label` ("REPLAY") junto a la velocidad elegida, y `replay.disclaimer` literal, siempre visibles. Nunca decir ni insinuar inferencia en vivo; no poner botones tipo "ejecutar" ni spinners sin la etiqueta.
- Fase silenciosa: el razonamiento no se transmite. Hasta el primer carácter visible se muestra "razonando" con el reloj corriendo y sin texto. Entre 93 % y 94 % de los tokens de completion son razonamiento (Wonder 56498 de 60586 = 93.3 %; Spark 64332 de 68121 = 94.4 %), así que casi toda la espera es esa fase.
- Texto visible (`narrative_full`):
  - `v1-streamed-capture`: caracteres visibles en `t` = interpolación lineal entre los checkpoints `[t_ms, char_offset]` de `stream_timeline` (medidos del SSE; `timing_basis = measured_sse`).
  - `v0-artifact-derived`: no hay checkpoints. `estimated_ttft_ms = latency_ms × usage.reasoning / usage.completion` y el texto se reparte linealmente hasta `latency_ms` (`timing_basis = interpolated`). Rotular "timing interpolado".
- Los casos son escenarios de prueba escritos a mano en `legal_eval_harness.py`, no detecciones reales. El prompt del suite pide un "dictamen jurídico-marítimo" de 2 oraciones: la narrativa puede llamarse así a sí misma, pero la UI no usa esa palabra como rótulo propio. El texto lo generó un modelo: rotular "texto generado por un modelo", sin lenguaje de dictamen oficial o judicial, sin "telemetría satelital real" y sin presentar los 12 registros SAM existentes como detecciones SAR.

## Estado de los datos de hoy (v0)

Fuente: `backend/ml/meta_muse_sam31_benchmark_2026.json` (commit `b31d4ba`), 30 casos × 2 modelos, n = 1, llamadas entre 19:18:12 y 19:20:13 UTC del 2026-10-29 (timestamps UUIDv7 de los `request_id`).

Faltantes que obligan a una recaptura (cada uno está como `DQ-NN` en `data_quality.known_issues`): narrativa completa (solo hay 240 caracteres), TTFT y timeline, `model_served`, `finish_reason`, prompts guardados, hallazgos con posición. Además:

- `post_validator_adherence_percent = 100.0` es una constante del suite (DQ-01). No mostrarla.
- `model_served` es desconocido: el engine cae en silencio al otro modelo si falla (HTTP distinto de 200, excepción o contenido vacío) y mide la latencia desde antes del primer intento (DQ-03). La latencia máxima de Wonder (89961 ms) queda muy cerca de los 90 s del cliente httpx; ese timeout es por operación, no total, así que la cercanía es una señal débil y no prueba un reintento.
- Latencias medidas con hasta 8 solicitudes en paralelo y sin alternar modelos (DQ-04). Promedios: Wonder 28597.1 ms, Spark 11725.4 ms. Son indicativos (n = 1).
- El veredicto del suite se calcula sin `has_valid_license` ni `is_national_flag` (DQ-06): TC-LEG-019/020/021 divergen de `expected_rule`.
- El prompt entrega los 5 valores exactos (DQ-07). Con él, un hallazgo mide fidelidad de copia, no razonamiento, y un validador corregido encontrará casi 0 errores reales. De ahí `synthetic_probe`: texto alucinado del harness (ADV-023..030), con `is_model_output = false` y rotulado así en la UI. Opcional: brazo B con prompt con distractores (necesita su propio OK de gasto).

### Auditoría del validador heredado (reproducible con `audit_validator_fp.py`)

Hoy el artefacto marca 15 de 60 resultados como `is_valid_raw = false` (Wonder 4, Spark 11).

- Sobre los 240 caracteres guardados, 11 de esos 15 son reproducibles y sus 16 hallazgos son falsos positivos leyendo el contexto: 11 por una letra de hemisferio pegada a una palabra (`-001 en` de "TC-EEZ-001 en latitud" leído como longitud -1.0; `200 en` de "Milla 200 en el Agujero Azul" leído como longitud 200), 4 por `-57.1 se` leído como latitud, y 1 por "submarino" en una frase que lo descarta (TC-ADV-029, Spark).
- Los otros 4 (Wonder: TC-LEG-022, TC-ADV-029, TC-ADV-030; Spark: TC-ADV-030) tienen el hallazgo fuera de los 240 caracteres: no se pueden juzgar.
- La diferencia 4 contra 11 sale del estilo de redacción de Spark ("El contacto TC-… en latitud …"), no de la calidad. No usarla en el arena.
- En los 8 textos del harness el validador da 14 hallazgos; 2 son colisiones de "m" con "millas" (ADV-023 y ADV-027), y "12 millas de mar territorial" (ADV-027) cuenta además como distancia.
- La paridad de conteo entre `reference_validator_spans.py` y el validador real es total en todas esas pruebas.

## Cambios al suite para la recaptura (v1)

Archivos: `scripts/run_meta_full_evaluation_suite.py` y `backend/app/laya/meta_muse_engine.py`. No tocar `temperature = 0.1` ni `max_tokens = 4096` del suite original, para que sea comparable (la mayor completion de hoy fue 3365 de 4096).

Parámetros de la API de Meta (leídos el 2026-10-29):

- `max_tokens` es un alias obsoleto que se sigue aceptando; el parámetro principal es `max_completion_tokens` ([chat-completions](https://dev.meta.ai/docs/protocols/chat-completions)). Mantener `max_tokens = 4096`; si se renombra, VERIFY que la semántica sea idéntica (el tope cuenta razonamiento + salida visible, [reasoning](https://dev.meta.ai/docs/reasoning)).
- `reasoning_effort` existe como parámetro de primer nivel con valores `minimal`, `low`, `medium`, `high`, `xhigh`, `max`; `none` devuelve HTTP 400 en Wonder y Spark, y `max` no sirve en el modelo contributor ([reasoning](https://dev.meta.ai/docs/reasoning)). El suite de hoy no lo envía: tampoco enviarlo en la recaptura, para comparar con los datos de hoy (`provenance.reasoning_effort = null`). El nivel por defecto de cada modelo no está documentado (VERIFY). Cambiarlo es otra corrida, con su propio gasto.
- `n` mayor que 1 devuelve HTTP 400: una corrida por caso y modelo.
- Modo Contributor (`muse-spark-1.3-contributor`) fuera de alcance: no mezclarlo con los datos Standard.

1. Streaming: `stream: true` y `stream_options: {include_usage: true}`. `stream_options.include_usage` no figura en la documentación de Meta (VERIFY en la prueba de humo; si no devuelve `usage` en el último chunk, el streaming no sirve para el costo y hay que medir la latencia en streaming y los tokens en una llamada sin streaming). Parsear SSE (el engine ya lo hace para sam-3.1). Por cada delta de texto visible guardar `t_ms` (perf_counter desde antes de enviar) y los caracteres UTF-16 acumulados de la narrativa NFC; fusionar checkpoints separados por menos de 50 ms, conservar el primero y el último.
2. `time_to_first_token_ms` = `t_ms` del primer delta no vacío (fin de la fase silenciosa).
3. `model_served` = campo `model` de la respuesta, no el pedido. La documentación lo muestra solo en la respuesta sin streaming; que los chunks SSE lo traigan es VERIFY (si no, hacer la prueba de humo sin streaming y comparar `model`). Si difiere de `model_requested`, la corrida se marca y no entra al arena.
4. Sin fallback al otro modelo (`provenance.fallback_disabled = true`) y timeout del cliente mayor al máximo observado (propuesta: 300 s).
5. Guardar `narrative_full` completa (`narrative_truncated = false`), `finish_reason`, `usage` con `reasoning` (`completion_tokens_details.reasoning_tokens`) y `cached_prompt` (`prompt_tokens_details.cached_tokens`, [prompt-caching](https://dev.meta.ai/docs/prompt-caching); el cache es automático) si vienen, `request_id`, y system + user por caso (`prompt.sha256`, `reconstructed = false`). Una corrida con `finish_reason = length` se registra tal cual.
6. Pasar `has_valid_license` e `is_national_flag` del escenario a `evaluate_maritime_case`.
7. Correr en serie y alternando el orden de los modelos por caso (W,S / S,W). Tiempo estimado: suma de las latencias de hoy = 857.9 s + 351.8 s = 1209.7 s, unos 20 minutos.
8. Validar cada narrativa con el validador corregido (sección siguiente), guardando `validator.findings` con `char_start`/`char_end`, y marcar `status = verified` solo si los tests pasan.
9. La clave sale de una variable de entorno y no se escribe en ningún archivo, log ni en el JSON; el JSON solo lleva `request_id`.
10. Escribir `arena_replay.json` de forma atómica y no commitear hasta que `validate_arena.py --selftest` pase. Antes de la corrida completa: prueba de humo con TC-EEZ-001 en ambos modelos para confirmar los tres puntos VERIFY de arriba (`include_usage`, `model` en chunks, `reasoning_tokens` en el `usage` final con streaming); ninguno está confirmado en la documentación de Meta.
11. Cortes: máximo 2 reintentos por llamada; 3 fallos seguidos abortan y se informa el error sin reintentar más.

## Validador: API con spans y arreglos antes de la recaptura

API: `validate_with_spans(texto, evidencia) -> (texto_nfc, hallazgos)`, con `rule_id`, `field`, `expected`, `observed`, `matched_text`, `char_start`, `char_end` (UTF-16, intervalo `[inicio, fin)` sobre el texto NFC), `severity` y `legacy_severity`. Implementación de referencia en `reference_validator_spans.py`; el schema fija los `rule_id` válidos.

Arreglos pedidos al validador del repo (cada uno con su test; los 16 falsos positivos de arriba son los tests de regresión y deben dar 0 hallazgos):

- F1. Hemisferio solo como token: la letra N/S/E/W/O no puede seguir una letra (`(?![^\W\d_])`) y el número no puede ir pegado a un identificador (`(?<![\w.-])` antes del signo). Deben seguir detectándose `45.2 S`, `45.2°S`, `25.50N`, `40.20W`.
- F2. La unidad `m` exige no ir seguida de letra, así "12 millas" no cuenta como 12 m. Las millas seguidas de "de mar territorial" o "de zona" son un límite legal, no una distancia medida.
- F3. Las reglas semánticas (submarino, mar territorial / 12 millas, paso inocente, piratería) no disparan si la misma oración las niega o refuta ("no", "descarta", "incompatible con", "sin", "ni"). Es heurística: lo ambiguo no cuenta.
- F4. Validar RCS contra `peak_rcs_db`. El prompt prohíbe citar otros dB, así que todo número en dB debe coincidir. Tolerancia propuesta: 0.5 dB (decisión pendiente).
- F5. Recortar espacios del `matched_text` ("12 millas " hoy sale con espacio final) y enmascarar IDs `TC-XXX-NNN` con relleno de igual largo antes de extraer, para no mover los offsets.
- F6. Los hallazgos se cuentan, y `adherence_percent = max(0, 100 − 15n)` es una penalización, no exactitud. La UI no la muestra como "porcentaje de acierto".

Hasta que F1 a F5 estén en el repo y probados, `validator.status` no puede ser `verified` y el lápiz rojo queda apagado (`ui_policy.red_pen_enabled = false`).

## Costo de la recaptura (30 casos × 2 modelos)

Precios por 1 M de tokens (modo Standard, https://dev.meta.ai/docs/pricing-rate-limits, leídos el 2026-10-29): Wonder entrada 4.00, salida 20.00; Spark entrada 1.25, salida 4.25. El razonamiento cuenta en el tope de salida y se cobra a la tarifa de salida según https://dev.meta.ai/docs/reasoning (la página de precios no lo dice). El caché de prompt es automático y da descuento sobre la entrada (https://dev.meta.ai/docs/prompt-caching, sin porcentaje en esa página); se ignora, así que es una cota superior. Modo Contributor excluido.

Fórmula: `costo = (prompt × entrada + completion × salida) / 1e6`. Con los tokens de hoy (prompt 5678 por modelo; completion 60586 y 68121):

| | cuenta | USD |
|---|---|---|
| Wonder | (5678 × 4.00 + 60586 × 20.00) / 1e6 = (22712 + 1211720) / 1e6 | 1.234432 |
| Spark | (5678 × 1.25 + 68121 × 4.25) / 1e6 = (7097.5 + 289514.25) / 1e6 | 0.296612 |
| Una pasada base | suma | 1.531044 |

- Es una estimación: asume tokens parecidos a los de hoy (n = 1, la variación entre corridas no está medida) y no aplica el descuento de caché (Wonder 0.20 y Spark 0.15 por 1 M de tokens de entrada cacheados, guardados en `provenance.price_source` sin usarse), así que es una cota superior. El 79 % del gasto es la salida de Wonder (1211720 de 1531043.75).
- Prueba de humo (1 caso, ambos modelos): unos 0.051 (1.531044 / 30).
- Con colchón 1.5×: 1.531044 × 1.5 = 2.30. Tope duro propuesto: 4.00, con el script cortando al acumular ese gasto.
- Máximo posible sin reintentos, si las 60 llamadas llegaran a `max_tokens = 4096`: (5678 × 4 + 30 × 4096 × 20) / 1e6 + (5678 × 1.25 + 30 × 4096 × 4.25) / 1e6 = 2.4803 + 0.5293 = 3.01.
- Brazo B opcional (prompt con distractores): otra pasada del mismo orden, unos +1.5 esperado y +3.0 como máximo por las salidas, más el costo de la entrada extra de los distractores (no estimado). Se aprueba aparte.

**Puerta de gasto:** no se llama a api.meta.ai hasta que Gaston diga que sí a un monto concreto (hoy: 1.53 esperado, 2.30 con colchón, tope 4.00; el brazo B, aparte).

## Pitch Mode (beats B5 y B6 de `specs/pitch/pitch_90s.md`)

- Contenedor `#replayArena`. Si el elemento no existe, el pitch usa el texto de fallback y no hay highlight. El pitch no lee números de este archivo: sus cifras (26 de 30 y 19, 98 y 92 %, 28.6 y 11.7 s, 24 % del costo estimado, "una corrida, 30 casos") salen de `stats.json`. Si el arena muestra un cociente propio, sale de las mismas fórmulas de la tabla de arriba (por ejemplo costo Wonder / Spark = 1.234432 / 0.296612 = 4.162 sobre los 30 casos) y se rotula "indicativo".
- Evento `pitch:arena` (CustomEvent sobre `document`) con `detail.phase`: `accuracy` (B5) arranca el replay del caso destacado a `replay.default_speed`, con el rótulo REPLAY y el `disclaimer`; el lápiz rojo solo aparece si `validator.status = verified`, si no se muestra el texto sin marcas. `speed` (B6) deja corriendo los relojes, tokens y costo estimado de ambos lados hasta que termine el más lento. Un evento nuevo reinicia el replay. El pitch no emite evento de salida: el arena corre su propio reloj y se detiene con sus controles. A x8, los 28.6 s promedio de Wonder se reproducen en unos 3.6 s.
- El arena no llama a la API ni muestra botones de ejecución durante el pitch. La puerta de gasto de abajo es independiente: sin el OK de Gaston no hay captura v1, y el pitch se graba con los datos v0 rotulados "timing interpolado".
- Ver la regla de la distancia a la ZEE en Notas de UI: el pitch no la dice ni la subtitula; solo aparece dentro de la tarjeta del escenario, rotulada.

## Notas de UI

- Todo texto de modelo (`narrative_full`, `matched_text`, `observed`, `expected`, `synthetic_probe.text`) se inserta con `textContent`. Nada de `innerHTML`, `insertAdjacentHTML` ni atributos construidos por concatenación (XSS). Recomendado: CSP por `<meta>` con `default-src 'self'`.
- Lápiz rojo: cortar `narrative_full` con `slice(char_start, char_end)` (JS usa UTF-16, igual que los offsets), crear `<span>` por segmento con `textContent`, y el rótulo "esperado X / dijo Y". En las reglas `NUM-*`, `expected` y `observed` son números: mostrarlos tal cual, con `field` rotulado (tabla más abajo). En las reglas `SEM-*`, `expected` es un enum crudo del motor (zona, clasificación, código de infracción): pasarlo por la tabla de rótulos; `observed` es la frase literal del texto. Los spans pueden solaparse: dividir en segmentos en cada borde y listar todos los hallazgos del segmento.
- Sin lápiz rojo si `narrative_truncated = true` o `validator.status` no es `verified`. Con `findings_available = false` no se afirma "sin errores".
- `synthetic_probe` va con su `label_es` y fuera del carril de los modelos.
- Distancia a la ZEE: cada escenario trae un valor dado, escrito a mano en el harness (`ground_truth.distance_to_eez_nm`), y el título y las narrativas lo citan (TC-EEZ-001: "a 86.47 NM dentro de la ZEE"). Mostrarlo siempre con el rótulo "Escenario de prueba: valor dado, no medido" y nunca asociarlo a detecciones, dossiers ni registros SAM de la escena sintética. El -86.47 NM de TC-EEZ-001 no está contrastado con `data/argentina_eez.geojson` (VERIFY). `replay.featured_case_id` del ejemplo es TC-EEZ-001 solo para maquetar; el caso destacado de la grabación del pitch lo elige Gaston (TC-SKM-010 es un caso de borde escrito a mano, a 0.05 NM).
- n = 1 por caso: toda comparación entre modelos se rotula "indicativa". No mostrar conteos agregados de marcas del validador mientras el estado no sea `verified`, ni las palabras "alucinación" o "100 %" / "0.00 %" como literales.

- Ubicación y carga: publicar como `docs/data/arena_replay.json` (lo que sirve GitHub Pages) y copiarlo byte a byte a `frontend/data/` y a `data/` de la raíz, igual que `stats.json` (`specs/stats/README.md`); el snapshot no trae script de sincronización: copiar a mano y comprobar con `cmp`. Desde `docs/app/index.html` (servido bajo `/OceanEye-hackaton-meta/app/`, con la barra final) cargar con `fetch('../data/arena_replay.json')`: ruta relativa sin barra inicial. Con `/data/...` apunta a la raíz del dominio y falla bajo el subpath del proyecto, y `./data/...` falla porque `docs/app/` solo tiene `index.html`. Es el primer camino del cargador del benchmark Muse en `docs/app/index.html` (línea 2935). Si el fetch o el parseo fallan, mostrar un mensaje visible y no romper el resto de la app. Antes de renderizar, comprobar `schema_version` y `provenance.dataset_version`.
- Enums crudos: nunca mostrar tal cual los valores de `scenario.ground_truth.jurisdiction_zone`, `classification`, `expected_rule_id` ni `expected_severity`. Usar esta tabla de rótulos (son escenarios de prueba del proyecto, no dictámenes):

| Valor del JSON | Rótulo en pantalla |
|---|---|
| `AGUAS_INTERIORES` | Aguas interiores |
| `MAR_TERRITORIAL_12NM` | Mar territorial (12 NM) |
| `ZONA_CONTIGUA_24NM` | Zona contigua (24 NM) |
| `ZONA_ECONOMICA_EXCLUSIVA_200NM` | Zona económica exclusiva (200 NM) |
| `ZONA_AMORTIGUACION_FRONTERIZA_3NM` | Amortiguación fronteriza (hasta 3 NM fuera de la ZEE) |
| `ALTA_MAR_ADYACENTE_MILLA_201` | Alta mar adyacente a la ZEE |
| `DARK_VESSEL` | Buque sin AIS |
| `GHOST_AIS` | AIS sin eco de radar |
| `COOPERATIVE_VESSEL` | Buque que transmite AIS |
| `CRITICAL_SOVEREIGN_VIOLATION` | Severidad del escenario: crítica |
| `HIGH_IUU_PROBABILITY` | Severidad del escenario: alta |
| `MODERATE_TELEMETRY_ANOMALY` | Severidad del escenario: moderada |
| `COMPLIANT_NAVIGATION` | Severidad del escenario: sin infracción |
| `RULE-…` | "Regla del motor: RULE-…" con el id literal (código del proyecto, no norma oficial) |
| `INCURSION_IUU_ZEE_ART51` (`ground_truth.infraction_code`) | Ingreso sin permiso a la ZEE |
| `SKIMMING_BORDER_PREDATORIO` | Pesca pegada al límite de la ZEE |
| `BLACKOUT_TACTICO_ALTA_MAR` | AIS apagado en alta mar |
| `SPOOFING_TELEMATICO_GHOST_AIS` | AIS sin eco de radar |
| `NAVEGACION_COOPERATIVA_CONFORME` | Navegación cooperativa |
| `CUMPLIMIENTO_NORMATIVO` (como `expected` de `SEM-DEFAM-001`) | Navegación cooperativa |
| `field`: `latitude`, `longitude`, `distance_to_eez_nm`, `length_m`, `peak_rcs_db` | latitud, longitud, distancia al límite de la ZEE (NM), eslora (m), RCS (dB) |
| `field`: `legal_characterization`, `jurisdiction_zone`, `economic_penalty_usd`, `vessel_type`, `infraction` | caracterización, zona, monto, tipo de buque, infracción |

  Un valor fuera de la tabla se muestra como "sin rótulo" y se registra en consola; no se imprime el valor crudo. Para llamar a `validate_with_spans` basta con pasar `scenario.ground_truth` (trae `infraction_code`). No mostrar `economic_penalty_max_usd` ni `beam_m` (en TC-EEZ-001 el harness trae `beam_m` igual a `length_m`, 41.5, que no es creíble y el prompt no lo usa).

Cada número visible sale de una ruta del JSON con una fórmula (`m` = modelo, `i` = caso):

| Se muestra | Ruta | Fórmula |
|---|---|---|
| Velocidad | `replay.default_speed`, `replay.speed_options` | valor elegido, con `replay.label` |
| Reloj del lado | `cases[i].runs[m].latency_ms` | `min(t_replay, latency_ms) / 1000` s |
| Tokens en vivo | `…usage.completion` | `round(completion × min(1, t_replay / latency_ms))`, rotulado "proporcional"; al final, `usage.completion` exacto |
| Razonamiento | `…usage.reasoning` | solo al final, "incluido en los tokens" |
| Costo en vivo | `…usage.prompt`, `…usage.completion`, `provenance.price_source.usd_per_1m_tokens` | `(prompt × entrada + tokens_en_vivo × salida) / 1e6`; al final, `cost_usd_estimate`; rotulado "estimado" |
| "Wonder tardó N× más" | `…latency_ms` de ambos lados | cociente a 1 decimal, "indicativo" |
| "Wonder costó N× más" | `…cost_usd_estimate` de ambos lados | cociente a 1 decimal, "indicativo" |
| Texto escrito | `…narrative_full`, `…stream_timeline` o `…interpolation` | ver Semántica |
| Esperado / dijo | `…validator.findings[].expected` y `observed` | `NUM-*`: literales; `SEM-*`: `expected` por la tabla de rótulos, `observed` literal |
