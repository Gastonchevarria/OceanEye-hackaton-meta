# 🌊 OceanEye — Platform Intel & IUU Fishing Detection (BNA 2026 Edition)

<div align="center">
  <img src="https://raw.githubusercontent.com/tandpfun/skill-icons/main/icons/Python.svg" height="40" alt="python logo" />
  <img width="12" />
  <img src="https://raw.githubusercontent.com/tandpfun/skill-icons/main/icons/FastAPI.svg" height="40" alt="fastapi logo" />
  <img width="12" />
  <img src="https://raw.githubusercontent.com/tandpfun/skill-icons/main/icons/PostgreSQL-Dark.svg" height="40" alt="postgres logo" />
  <img width="12" />
  <img src="https://raw.githubusercontent.com/tandpfun/skill-icons/main/icons/Docker.svg" height="40" alt="docker logo" />
</div>

---

## 🌐 Live Deployments & Entorno de Producción

| Componente | Plataforma | URL / Endpoint | Estado |
| :--- | :--- | :--- | :--- |
| **Frontend Web** | Vercel Edge | [https://oceaneye-ai.com](https://oceaneye-ai.com) (espejo: [oceaneye-two.vercel.app](https://oceaneye-two.vercel.app)) | 🟢 Operativo |
| **Backend API** | Google Cloud Run | [https://oceaneye-backend-29923645081.us-central1.run.app](https://oceaneye-backend-29923645081.us-central1.run.app) | 🟢 Operativo (Min instances: 0) |
| **API Healthcheck** | Cloud Run | [`/health`](https://oceaneye-backend-29923645081.us-central1.run.app/health) | 🟢 200 OK (DB + AIS + GFW + AI) |
| **Flota en Vivo** | Supabase + TimescaleDB | [`/api/v1/fleet/live`](https://oceaneye-backend-29923645081.us-central1.run.app/api/v1/fleet/live) | 🟢 150+ Buques Streaming |
| **Benchmark SAR** | Sentinel-1 GRD Dual-Pol | [`/api/v1/sar/benchmark`](https://oceaneye-backend-29923645081.us-central1.run.app/api/v1/sar/benchmark) | 🟢 15 Detecciones / 12 Dark |
| **Kit de Verificación** | GitHub (Público) | [https://github.com/Gastonchevarria/oceaneye-evaluation](https://github.com/Gastonchevarria/oceaneye-evaluation) | 🟢 Verificable en 1 comando |

---

## 🏆 Proyecto Postulado a las Becas Leonardo 2026 (Fundación BBVA)
**Área**: *Ciencias de la Computación, Ciencia de Datos e Inteligencia Artificial* / *Tecnología Limpia (Cleantech) y Biodiversidad*  
**Convocatoria Oficial**: [https://www.programaleonardo.com/](https://www.programaleonardo.com/) — [Bases Oficiales](concursoBBVA.pdf)

**OceanEye** es una plataforma de inteligencia marítima y soberanía geoespacial impulsada por teledetección satelital (Sentinel-1 SAR), inteligencia artificial generativa y monitoreo de telemetría AIS en tiempo real. Está diseñada para detectar, correlacionar y tipificar jurídicamente la pesca ilegal, no declarada y no reglamentada (INDNR / IUU Fishing) en el Atlántico Sur y el Agujero Azul (Milla 201), aportando evidencia pericial con cadena de custodia criptográfica SHA-256 ante el Régimen Federal de Pesca (Ley 24.922).

---

## 🚀 Arquitectura de Producción

```
                      ┌──────────────────────────────┐
                      │    WebSocket AISStream.io    │
                      └──────────────┬───────────────┘
                                     │
                                     ▼
                      ┌──────────────────────────────┐
                      │   Worker AIS 24/7 (Worker)   │
                      │  `workers/ais_ingestor.py`   │
                      └──────────────┬───────────────┘
                                     │
                                     ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │                  PostgreSQL / Supabase + TimescaleDB             │
   │  Tables: vessel_positions (Hypertable) | vessel_profiles | alerts │
   └─────────────────────────────────┬────────────────────────────────┘
                                     │
                                     ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │                      FastAPI Backend API (Cloud Run)                 │
 │  `/vessels` | `/analyze` | `/chat` | `/briefing` | `/alerts`       │
 └───────────────────────────────────┬──────────────────────────────────┘
                                     │
                                     ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │                   Artificial AI Engine (Resilience Chain)             │
 │  Multi-model inference with automatic failover                       │
 │  3-level fallback for zero-downtime intelligence analysis            │
 └──────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Componentes Clave

- **Base de Datos Espacio-Temporal**: PostgreSQL + TimescaleDB (Supabase) con retención automática de 90 días para millones de posiciones AIS.
- **Worker 24/7 Ininterrumpido**: Proceso independiente que ingiere transmisiones AIS de la ZEE Argentina, calcula heurísticas de riesgo en tiempo real y genera alertas inmediatas.
- **Motor de IA (Artificial AI)**: Sistema multi-modelo con tolerancia a fallos para análisis tácticos en lenguaje natural, reportes de inteligencia y chatbot conversacional.
- **Enriquecimiento GFW**: Integración directa con Global Fishing Watch API para correlación de eventos de loitering, vacíos AIS (dark vessels) y visitas a puerto.

---

## 📦 Despliegue y Ejecución

### 1. Base de Datos (Supabase)
Ejecutar la migración SQL `backend/alembic/versions/001_init.sql` en el Editor SQL de Supabase.

### 2. Backend FastAPI
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 3. Worker AIS 24/7
```bash
cd backend
python -m workers.ais_ingestor
```

---

## 🌐 Frontend
Distribuido en Vercel. Conecta de forma transparente con el backend FastAPI via `window.OCEANEYE_API_BASE`.

---

## 🛰️ Módulo de Teledetección Radar SAR & Convocatoria Becas Leonardo BBVA 2026

OceanEye v2.0 incorpora el pipeline de física de radar y teledetección satelital para la detección de buques no reglamentados en el Atlántico Sur (Milla 201):

### ⚡ Evaluación Rápida Offline para el Jurado (< 2.5s)
El repositorio incluye una sub-escena calibrada Sentinel-1 IW GRD Dual-Pol (VV + VH) pre-empaquetada en `backend/tests/fixtures/`. Para correr el pipeline completo sin requerir tokens ni descargas externas:

```bash
cd backend
pytest tests/test_e2e_pipeline.py -s
```

**Resultados de la Ejecución de Prueba**:
- Tiempo de ejecución: **~2.4 segundos**
- Blancos físicos detectados: **15**
- Buques legales confirmados (SAR + AIS): **3**
- **Pesqueros Oscuros (Dark Vessels) identificados**: **12 / 12**
- **Suplantación de Identidad (Ghost AIS Spoofing)**: **1**
- **Cadena de Custodia Criptográfica**: 12 Dossiers con sellos SHA-256 generados

### 📜 Documentación Científica y Jurídica
- **Memoria Técnica Completa**: Consulte [`docs/MEMORIA_TECNICA_BBVA.md`](docs/MEMORIA_TECNICA_BBVA.md) para el desglose matemático, físico, algorítmico y presupuestario.
- **Límite Náutico Oficial (Milla 200)**: Definido en [`frontend/data/argentina_eez.geojson`](frontend/data/argentina_eez.geojson) según el Servicio de Hidrografía Naval (SHN) y Ley 23.968.
- **Endpoints REST**:
  - `GET /api/v1/sar/benchmark`: Benchmark instantáneo sin credenciales.
  - `POST /api/v1/sar/analyze`: Ingesta STAC COG en tiempo real con fallback resiliente.
  - `GET /api/v1/sar/dossier/{target_id}`: Generación de certificado pericial SHA-256.
  - `GET /api/v1/sar/eez/boundary`: GeoJSON oficial de la ZEE Argentina.
