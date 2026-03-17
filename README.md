# PE Org-AI-R Platform

**AI-Readiness Assessment Platform for Private Equity Portfolio Companies**

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com)
[![Tests](https://img.shields.io/badge/Tests-255%20passed-brightgreen.svg)]()
[![Coverage](https://img.shields.io/badge/Coverage-97%25-brightgreen.svg)]()

---

## Links

| Resource | URL |
|----------|-----|
| **Codelabs Document** | https://codelabs-preview.appspot.com/?file_id=1ZYVD62sCK0jvl3ffeBwXGa9qtkbn3vXAYPjzNQhwtow#0 |
| **Video Presentation** | https://youtu.be/2NXjSDy71eM |
| **Live Application** | http://54.172.44.67:8501 |

---

## Project Overview

The PE Org-AI-R platform enables private equity firms to systematically assess the AI-readiness of portfolio companies using a data-driven scoring framework. It collects evidence from 9 real data sources, maps them to 7 AI-readiness dimensions, produces calibrated Org-AI-R scores with confidence intervals, and generates **cited score justifications** for Investment Committee review via a hybrid RAG pipeline.

### Case Studies Implemented

| Case Study | Focus | Key Components |
|------------|-------|---------------|
| **CS1** | API & Database Design | FastAPI REST API, Snowflake schema, Redis caching, Pydantic models |
| **CS2** | Evidence Collection | SEC EDGAR filings, job postings, patents, tech stack signals |
| **CS3** | AI Scoring Engine | Evidence mapper, rubric scorer, VR/HR/Synergy calculations, 5-company portfolio |
| **CS4** | RAG & Search | Hybrid retrieval (Dense+BM25+RRF), LLM-powered score justifications, IC meeting prep, analyst notes |

**Course**: DAMG 7245 — Big Data and Intelligent Analytics (Spring 2026)

### Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend API** | Python 3.12, FastAPI, Pydantic v2 |
| **CS4 RAG API** | FastAPI (port 8003), LiteLLM, ChromaDB, sentence-transformers, BM25 |
| **Database** | Snowflake (cloud data warehouse) |
| **Vector Store** | ChromaDB (persistent, cosine similarity, metadata filtering) |
| **Embeddings** | sentence-transformers (all-MiniLM-L6-v2, 384-dim) |
| **LLM Routing** | LiteLLM (100+ providers, automatic fallbacks, cost tracking) |
| **Cache** | Redis 7 (Alpine) |
| **Frontend** | Streamlit 1.54, Plotly |
| **Orchestration** | Apache Airflow 2.8 (with pool-based concurrency control) |
| **Containerization** | Docker Compose (8 services) |
| **Testing** | Pytest, Hypothesis (property-based) |
| **External APIs** | SEC EDGAR, Wextractor (Glassdoor), sec-api.io (Board), USPTO PatentsView, GNews, python-jobspy |

---

## Architecture

### Docker Compose Stack

```mermaid
graph TB
    subgraph Docker["Docker Compose Stack (8 Services)"]
        subgraph Frontend
            ST["🖥️ Streamlit<br/>Port 8501"]
        end

        subgraph APIs["API Layer"]
            API["⚡ FastAPI CS1-CS3<br/>Port 8000"]
            CS4["🧠 CS4 RAG API<br/>Port 8003"]
        end

        subgraph Storage
            SF[("❄️ Snowflake<br/>Cloud DW")]
            RD[("🔴 Redis<br/>Port 6379")]
            CR[("🟣 ChromaDB<br/>Vector Store")]
        end

        subgraph Airflow["Apache Airflow"]
            AW["🌐 Webserver<br/>Port 8080"]
            AS["⏰ Scheduler"]
            PG[("🐘 PostgreSQL<br/>Port 5432")]
        end

        subgraph LLM["LLM Providers"]
            GPT["OpenAI<br/>gpt-4o / gpt-4o-mini"]
            FB["Fallback<br/>gpt-3.5-turbo"]
        end
    end

    ST --> API
    ST --> CS4
    API --> SF
    API --> RD
    CS4 --> API
    CS4 --> CR
    CS4 --> GPT
    CS4 -.-> FB
    AW --> PG
    AS --> PG
    AS --> API
    AS --> CS4

    EXT["📡 External APIs<br/>SEC EDGAR · Wextractor · sec-api.io<br/>USPTO · GNews · python-jobspy"] --> API

    style Docker fill:#1a1a2e,stroke:#16213e,color:#fff
    style Frontend fill:#0f3460,stroke:#533483,color:#fff
    style APIs fill:#16213e,stroke:#0f3460,color:#fff
    style Storage fill:#1a1a2e,stroke:#533483,color:#fff
    style Airflow fill:#1a1a2e,stroke:#e94560,color:#fff
    style LLM fill:#0f3460,stroke:#533483,color:#fff
```

### Complete Data Pipeline (CS1 → CS2 → CS3 → CS4)

```mermaid
graph LR
    subgraph Sources["📡 Evidence Sources"]
        SEC["SEC EDGAR<br/>10-K, 10-Q, 8-K"]
        JOBS["Job Boards<br/>Indeed"]
        PAT["USPTO<br/>Patents"]
        GD["Glassdoor<br/>Reviews"]
        BD["Board Data<br/>sec-api.io"]
        TECH["Tech Stack<br/>Analysis"]
        NEWS["GNews<br/>Press Releases"]
    end

    subgraph CS2["CS2: Evidence Mapper"]
        EM["9 Sources →<br/>6 Signal Categories"]
    end

    subgraph CS3["CS3: Scoring Engine"]
        DIM["7 Dimensions"]
        VR["VR Calculator"]
        HR["HR Calculator"]
        SYN["Synergy"]
        SCORE["Org-AI-R<br/>Score"]
    end

    subgraph CS4["CS4: RAG & Search"]
        IDX["ChromaDB +<br/>BM25 Index"]
        HYB["Hybrid<br/>Retrieval + RRF"]
        JUST["Score<br/>Justification"]
        IC["IC Meeting<br/>Package"]
    end

    SEC --> EM
    JOBS --> EM
    PAT --> EM
    GD --> EM
    BD --> EM
    TECH --> EM
    NEWS --> EM

    EM --> DIM
    DIM --> VR
    DIM --> HR
    VR --> SYN
    HR --> SYN
    SYN --> SCORE

    EM --> IDX
    SCORE --> JUST
    IDX --> HYB
    HYB --> JUST
    JUST --> IC

    style Sources fill:#1e3a5f,stroke:#4a90d9,color:#fff
    style CS2 fill:#2d5a27,stroke:#4a9940,color:#fff
    style CS3 fill:#5a3d27,stroke:#d9904a,color:#fff
    style CS4 fill:#4a2760,stroke:#9940d9,color:#fff
```

### CS4 RAG Justification Pipeline

```mermaid
graph TD
    Q["❓ Why did NVDA score 94<br/>on Data Infrastructure?"]

    Q --> S1["1️⃣ Fetch Score from CS3<br/>93.7/100 = Level 5 Excellent"]
    Q --> S2["2️⃣ Fetch Rubric from CS3<br/>Keywords: snowflake, real-time,<br/>data quality, streaming"]

    S1 --> S3["3️⃣ Build Search Query<br/>from Rubric Keywords"]
    S2 --> S3

    S3 --> HYDE{"HyDE<br/>Enabled?"}
    HYDE -->|"Yes (LLM)"| HY["Generate Hypothetical<br/>Evidence Passage"]
    HYDE -->|"No"| RAW["Use Raw Query"]

    HY --> DENSE["🔵 Dense Retrieval<br/>ChromaDB Cosine<br/>Similarity"]
    RAW --> DENSE
    S3 --> SPARSE["🟠 Sparse Retrieval<br/>BM25 Keyword<br/>Matching"]

    DENSE --> RRF["⚡ RRF Fusion<br/>score = Σ w/(k + rank)<br/>Dense=0.6 · Sparse=0.4 · k=60"]
    SPARSE --> RRF

    RRF --> MATCH["5️⃣ Match Evidence<br/>to Rubric Keywords"]
    RRF --> GAPS["6️⃣ Identify Gaps<br/>Next Level Criteria"]

    MATCH --> LLM["7️⃣ GPT-4o Summary<br/>IC-Ready PE Memo"]
    GAPS --> LLM

    LLM --> OUT["📋 ScoreJustification<br/>Score · Rubric · Evidence<br/>Gaps · Summary · Strength"]

    style Q fill:#e74c3c,stroke:#c0392b,color:#fff
    style RRF fill:#8e44ad,stroke:#6c3483,color:#fff
    style LLM fill:#27ae60,stroke:#1e8449,color:#fff
    style OUT fill:#2980b9,stroke:#1f618d,color:#fff
```

### Airflow DAG Dependencies & Pool Control

```mermaid
graph TD
    subgraph DAG1["📡 evidence_collection_pipeline<br/>Sundays 4am UTC"]
        D1_START["start"] --> D1_POOL["setup_pool<br/>pe_api_pool = 3 slots"]
        D1_POOL --> D1_HEALTH["check_api_health<br/>+ baseline capture"]
        D1_HEALTH --> D1_CS2["CS2 Collection<br/>5 companies × pool=3"]
        D1_CS2 --> D1_CS3["CS3 Collection<br/>5 companies × pool=3"]
        D1_CS3 --> D1_VAL["validate_collection<br/>Data Quality Gate"]
        D1_VAL --> D1_END["end"]
    end

    subgraph DAG2["🎯 scoring_pipeline<br/>Mondays 6am UTC"]
        D2_START["start"] --> D2_WAIT["wait_for_evidence<br/>ExternalTaskSensor"]
        D2_WAIT --> D2_BASE["capture_baseline<br/>Drift Detection"]
        D2_BASE --> D2_SCORE["score_portfolio<br/>pool=pe_api_pool"]
        D2_SCORE --> D2_VAL["validate_results<br/>Ranges + Ranking"]
        D2_VAL --> D2_AGG["aggregate_portfolio<br/>Audit Report"]
        D2_AGG --> D2_END["end"]
    end

    subgraph DAG3["🔍 pe_evidence_indexing<br/>Daily 2am UTC"]
        D3_START["start"] --> D3_POOL["setup_pool"]
        D3_POOL --> D3_HEALTH["check_cs4_health<br/>+ pre-index stats"]
        D3_HEALTH --> D3_IDX["Index 5 Companies<br/>pool=3 concurrent"]
        D3_IDX --> D3_VER["verify_index_stats<br/>Pre/Post Delta Report"]
        D3_VER --> D3_END["end"]
    end

    D1_END -.->|"ExternalTaskSensor"| D2_WAIT

    subgraph POOL["🏊 pe_api_pool (3 slots)"]
        PS["Max 3 concurrent<br/>API calls across<br/>all DAGs"]
    end

    D1_CS2 -.-> PS
    D1_CS3 -.-> PS
    D2_SCORE -.-> PS
    D3_IDX -.-> PS

    style DAG1 fill:#1a3a5c,stroke:#4a90d9,color:#fff
    style DAG2 fill:#3a1a5c,stroke:#9a4ad9,color:#fff
    style DAG3 fill:#1a5c3a,stroke:#4ad94a,color:#fff
    style POOL fill:#5c1a1a,stroke:#d94a4a,color:#fff
```

### LLM Multi-Model Routing (Task 7.1)

```mermaid
graph LR
    subgraph Tasks["Task Types"]
        T1["Justification<br/>Generation"]
        T2["Evidence<br/>Extraction"]
        T3["Chat / HyDE<br/>Generation"]
    end

    subgraph Router["LiteLLM Router<br/>+ Daily Budget $10"]
        R["ModelRouter.complete()"]
    end

    subgraph Models["Models"]
        M1["gpt-4o<br/>Best quality<br/>$2.50/1M tokens"]
        M2["gpt-4o-mini<br/>Fast + cheap<br/>$0.15/1M tokens"]
        M3["gpt-3.5-turbo<br/>Fallback<br/>$0.50/1M tokens"]
    end

    T1 --> R
    T2 --> R
    T3 --> R

    R -->|"primary"| M1
    R -->|"primary"| M2
    R -.->|"fallback"| M3

    style Tasks fill:#2c3e50,stroke:#3498db,color:#fff
    style Router fill:#8e44ad,stroke:#9b59b6,color:#fff
    style Models fill:#27ae60,stroke:#2ecc71,color:#fff
```

---

## Portfolio Results

| Company | Sector | Org-AI-R | VR | HR | Synergy | 95% CI | Expected | Status |
|---------|--------|----------|------|------|---------|--------|----------|--------|
| **NVIDIA** | Technology | **81.73** | 78.35 | 92.04 | 66.32 | [78.8, 84.7] | 85-95 | CI overlaps |
| **Walmart** | Retail | **66.98** | 66.13 | 75.22 | 46.54 | [64.0, 69.9] | 55-65 | Above by ~2 |
| **JPMorgan** | Financial | **63.06** | 55.18 | 83.87 | 36.73 | [60.1, 66.0] | 65-75 | CI overlaps |
| **GE** | Manufacturing | **59.66** | 55.50 | 74.22 | 35.25 | [56.7, 62.6] | 45-55 | Above by ~5 |
| **Dollar General** | Retail | **46.74** | 39.28 | 67.22 | 19.48 | [43.8, 49.7] | 35-45 | Above by ~2 |

*Ranking: NVDA > WMT > JPM > GE > DG ✓*

### CS4 IC Recommendation (NVDA Example)

| Field | Value |
|-------|-------|
| **Recommendation** | 🟢 PROCEED — Strong AI readiness with solid evidence base |
| **Org-AI-R** | 81.7 (VR=78.3, HR=92.0) |
| **Key Strengths** | Data Infrastructure (Level 5), Technology Stack (Level 5), AI Governance (Level 4) |
| **Key Gaps** | No evidence of CAIO, CDO, CTO AI roles |
| **Risk Factors** | No major risk factors identified |
| **Total Evidence** | 5,088 indexed documents (SEC chunks + Glassdoor + Board + News + Jobs) |

---

## Directory Structure

```
pe-org-air-platform/
├── app/                                 # CS1–CS3 Backend
│   ├── main.py                          # FastAPI application entry point
│   ├── config.py                        # Pydantic settings (env-based)
│   ├── models/                          # Pydantic data models
│   ├── routers/                         # FastAPI API endpoints
│   │   ├── health.py                    # GET /health
│   │   ├── companies.py                 # CRUD /api/v1/companies
│   │   ├── assessments.py               # CRUD /api/v1/assessments
│   │   ├── documents.py                 # CRUD /api/v1/documents
│   │   ├── signals.py                   # CRUD /api/v1/signals + /evidence
│   │   ├── rubrics.py                   # GET /api/v1/rubrics/{dimension}
│   │   └── pipeline.py                  # Pipeline execution & orchestration
│   ├── services/                        # Snowflake ORM, Redis cache, S3
│   ├── pipelines/                       # SEC EDGAR, Jobs, Patents, Glassdoor, Board, News
│   └── scoring/                         # CS3: Evidence mapper → Rubric → VR/HR/Synergy → Org-AI-R
│
├── src/                                 # CS4 RAG & Search
│   ├── config.py                        # CS4 settings (LLM config, retrieval tuning)
│   ├── services/
│   │   ├── integration/                 # CS1/CS2/CS3 API Clients
│   │   │   ├── cs1_client.py            # Company metadata (ticker → UUID resolution)
│   │   │   ├── cs2_client.py            # Evidence loader (Snowflake + local JSON enrichment)
│   │   │   └── cs3_client.py            # Scoring client (scores, rubrics, local fallback)
│   │   ├── llm/router.py               # LiteLLM multi-provider router + budget tracking
│   │   ├── search/vector_store.py       # ChromaDB with metadata filtering
│   │   ├── retrieval/
│   │   │   ├── dimension_mapper.py      # Signal → Dimension mapping (PDF Table 1)
│   │   │   ├── hybrid.py               # Dense + BM25 + RRF fusion
│   │   │   └── hyde.py                  # Hypothetical Document Embeddings
│   │   ├── justification/generator.py   # Score justification with cited evidence
│   │   ├── workflows/ic_prep.py         # IC meeting prep (asyncio.gather, 7 dims)
│   │   └── collection/analyst_notes.py  # DD evidence collector (4 note types)
│   └── api/                             # CS4 FastAPI endpoints
│       ├── search.py                    # Search, index, stats, LLM status
│       └── justification.py             # Justification, IC prep, analyst notes
│
├── cs4_api.py                           # CS4 FastAPI app (port 8003)
├── streamlit_app.py                     # 14-page Streamlit dashboard
├── airflow/dags/                        # 3 DAGs with pool-based concurrency
│   ├── evidence_collection_dag.py       # CS2+CS3 collection (pool-limited)
│   ├── scoring_pipeline_dag.py          # Scoring + validation + drift detection
│   └── evidence_indexing_dag.py         # CS4 nightly indexing (pool-limited)
├── tests/                               # 255+ tests (CS1-CS4)
├── docker/
│   ├── compose.yaml                     # 8-service Docker Compose
│   ├── Dockerfile                       # FastAPI container
│   ├── Dockerfile.cs4                   # CS4 RAG API container
│   └── Dockerfile.streamlit             # Streamlit container
├── results/                             # Portfolio scoring outputs (JSON)
├── data/                                # Cached evidence (Glassdoor, Board, News)
└── chroma_data/                         # ChromaDB persistent vector store
```

---

## Setup Instructions

### Option 1: Docker Compose (Recommended)

```bash
# 1. Clone and configure
git clone <repository-url>
cd BigDataIA-SPring26-Team-4-case-study-4
cp .env.example .env
# Edit .env with Snowflake credentials, API keys, and OpenAI key

# 2. Build and start all 8 services
cd docker
docker compose up --build -d

# 3. Access applications
# Streamlit:     http://localhost:8501
# CS3 API Docs:  http://localhost:8000/docs
# CS4 RAG Docs:  http://localhost:8003/docs
# Airflow:       http://localhost:8080 (admin/admin)

# 4. Stop
docker compose down
```

### Option 2: Local Development

```bash
# 1. Install and configure
poetry install
cp .env.example .env  # Add credentials

# 2. Start services (3 terminals)
poetry run uvicorn app.main:app --reload --port 8000      # Terminal 1: CS3
poetry run uvicorn cs4_api:app --reload --port 8003        # Terminal 2: CS4
poetry run streamlit run streamlit_app.py                   # Terminal 3: UI

# 3. Run tests
poetry run pytest -v
```

### CS4 LLM Configuration

```bash
# .env — multi-model routing for different task types
CS4_PRIMARY_MODEL=gpt-4o-mini
CS4_FALLBACK_MODEL=gpt-3.5-turbo
CS4_JUSTIFICATION_MODEL=gpt-4o          # Best quality for IC memos
CS4_EXTRACTION_MODEL=gpt-4o-mini        # Fast + cheap for extraction
CS4_CHAT_MODEL=gpt-4o-mini              # Lightweight for HyDE + chat
OPENAI_API_KEY=sk-...
CS4_DAILY_BUDGET_USD=10.0
```

---

## Scoring Formulas

**Org-AI-R** = (1 − β) · [α · VR + (1 − α) · HR] + β · Synergy

| Formula | Expression | Constants |
|---------|-----------|-----------|
| **VR** | D̄w × (1 − λ × cv_D) × TalentRiskAdj | λ = 0.25 |
| **HR** | HR_base × (1 + δ × PF) | δ = 0.15 |
| **PF** | 0.6 × VR_component + 0.4 × MCap_component | bounded [-1, 1] |
| **Synergy** | VR × HR / 100 × Alignment × TimingFactor | TimingFactor ∈ [0.8, 1.2] |
| **Final** | (1 − β) × [α × VR + (1 − α) × HR] + β × Synergy | α=0.60, β=0.12 |

### CS4 Hybrid Retrieval Parameters

| Parameter | Value | Configurable Via |
|-----------|-------|-----------------|
| Dense Weight | 0.60 | `CS4_DENSE_WEIGHT` |
| Sparse (BM25) Weight | 0.40 | `CS4_BM25_WEIGHT` |
| RRF Constant (k) | 60 | `CS4_RRF_K` |
| Embedding Model | all-MiniLM-L6-v2 (384-dim) | `CS4_EMBEDDING_MODEL` |
| Candidate Multiplier | 3× | Hardcoded |
| HyDE Enhancement | Auto (requires LLM) | Falls back to raw query |
| Daily Budget | $10.00 | `CS4_DAILY_BUDGET_USD` |
| Airflow Pool Slots | 3 concurrent | `pe_api_pool` |

---

## API Endpoints

### CS1/CS2/CS3 API (Port 8000)

| Router | Prefix | Purpose |
|--------|--------|---------|
| `health.py` | `/health` | Health check (Snowflake/Redis/S3) |
| `companies.py` | `/api/v1/companies` | Company CRUD + ticker lookup |
| `assessments.py` | `/api/v1/assessments` | Assessment lifecycle |
| `documents.py` | `/api/v1/documents` | SEC document CRUD + chunks |
| `signals.py` | `/api/v1/signals` | External signal CRUD + evidence stats |
| `rubrics.py` | `/api/v1/rubrics` | Dimension rubric criteria |
| `pipeline.py` | `/api/v1/pipeline` | Pipeline execution, scoring, weights |

### CS4 RAG API (Port 8003)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/search` | GET | Hybrid search with metadata filters |
| `/api/v1/index` | POST | Index company evidence → ChromaDB + BM25 |
| `/api/v1/index/stats` | GET | Indexing statistics |
| `/api/v1/llm/status` | GET | LLM providers, models, daily budget |
| `/api/v1/justification/{company}/{dim}` | GET | Score justification with cited evidence |
| `/api/v1/ic-prep/{company}` | GET | Full IC meeting package (7 dimensions) |
| `/api/v1/analyst-notes/*` | POST/GET | Submit & list analyst notes (4 types) |
| `/health` | GET | Service health check |

---

## Streamlit Dashboard (14 Pages)

### CS2/CS3 Pages

| Page | Features |
|------|----------|
| 📊 Portfolio Overview | KPI metrics, bar charts with CI, VR/HR/Synergy breakdown |
| 🔍 Company Deep Dive | 7-dimension radar chart, score decomposition |
| 📐 Dimension Analysis | Heatmap, cross-company comparison, radar overlay |
| 📡 CS2 Evidence Dashboard | Signal weights, evidence stats, composite recalculation |
| ⚖️ Signal Weight Configurator | Interactive sliders, live preview, persist to Snowflake |
| 🚀 Pipeline Control | Run pipelines via API, progress tracking, task history |
| 🧮 Scoring Methodology | Formulas, Sankey diagram, dimension weights |
| 📂 Evidence Explorer | Direct API calls, 6 evidence tabs (SEC, Glassdoor, Board, Jobs, News) |
| 🧪 Testing & Coverage | Run pytest from UI, coverage chart, property test details |

### CS4 RAG & Search Pages

| Page | Features |
|------|----------|
| 🔎 Evidence Search | Hybrid retrieval, company/dimension/source filters, score-badged expandable cards |
| 📋 Score Justification | Score card, rubric match, GPT-4o IC-ready summary, cited evidence, gap identification |
| 📑 IC Meeting Prep | Recommendation badge, executive summary, strengths/gaps/risks, 7-dimension justifications |
| 📝 Analyst Notes | 4 note types (Interview, DD Finding, Data Room, Meeting), real-time indexing |
| ⚙️ RAG Settings | Service health, LLM status + budget, evidence indexing, index stats, API reference |

---

## Airflow DAGs (Pool-Controlled)

All DAGs share `pe_api_pool` (3 slots) to prevent backend overload — scales safely to 20+ companies.

| DAG | Schedule | Pool | Key Features |
|-----|----------|------|-------------|
| `evidence_collection_pipeline` | Sundays 4am | ✅ 3 slots | CS2+CS3 collection → **data quality validation gate** |
| `scoring_pipeline` | Mondays 6am | ✅ 3 slots | ExternalTaskSensor → score → **range validation** → **drift detection** → audit report |
| `pe_evidence_indexing` | Daily 2am | ✅ 3 slots | Health check → index (pooled) → **pre/post delta verification** |

**Why Airflow over Streamlit?** Streamlit is interactive (click-to-run). Airflow adds: scheduled automation, pool concurrency control, dependency chains (ExternalTaskSensor), data quality gates, drift detection, SLA monitoring, retry with exponential backoff, and full audit trail.

---

## Testing

```bash
poetry run pytest -v                          # Full suite
poetry run pytest tests/test_cs4_*.py -v      # CS4 only
poetry run pytest --cov=app/scoring --cov=src  # With coverage
```

| Metric | Value |
|--------|-------|
| Total Tests | 255+ |
| CS3 Scoring Coverage | 97% |
| Hypothesis Property Tests | 6 × 500 examples |
| CS4 Test Files | 4 (integration, rag, workflows, api) |

---

## Team Member Contributions

| Member | Contributions |
|--------|--------------|
| **Deep Prajapati** | CS1 API design, CS2 evidence collection (SEC, jobs, patents, tech), CS3 scoring engine (all 11 components), Glassdoor/Board/News collectors, CS4 RAG pipeline (hybrid retrieval, HyDE, justification generator, IC prep workflow, analyst notes), Streamlit dashboard (14 pages), Docker Compose (8 services), Airflow DAGs (3 DAGs with pool control), full integration testing |
| **Tapan Patel** | Airflow DAG design reference, initial Docker setup |
| **Seamus McAvoy** | CS1 API foundation, initial Snowflake schema design, CS2 evidence pipeline contributions |

### AI Tools Used

| Tool | Usage |
|------|-------|
| **Claude (Anthropic)** | Code generation, debugging, architecture design, formula verification, test writing, RAG pipeline design |
| **GitHub Copilot** | Inline code suggestions |

---

## Deliverables Checklist

### Lab 5 — CS3 Scoring (50 points)
- ✅ Evidence Mapper with complete mapping table (10 pts)
- ✅ Rubric Scorer with all 7 dimension rubrics (8 pts)
- ✅ Glassdoor Culture Collector (7 pts)
- ✅ Board Composition Analyzer (7 pts)
- ✅ Talent Concentration Calculator (5 pts)
- ✅ Decimal utilities (3 pts)
- ✅ VR Calculator with audit logging (5 pts)
- ✅ Property-based tests (5 pts)

### Lab 6 — CS3 Portfolio (50 points)
- ✅ Position Factor Calculator (5 pts)
- ✅ Integration Service — full pipeline (15 pts)
- ✅ HR Calculator with δ = 0.15 (5 pts)
- ✅ SEM-based Confidence Calculator (5 pts)
- ✅ Synergy Calculator (5 pts)
- ✅ Org-AI-R Calculator (5 pts)
- ✅ 5-company portfolio results (10 pts)

### Lab 7 — CS4 Foundation & Integration (33 points)
- ✅ CS1 Company Client (5 pts)
- ✅ CS2 Evidence Schema & Loader (8 pts)
- ✅ CS3 Scoring API Client (7 pts)
- ✅ LiteLLM Multi-Provider Router (8 pts)
- ✅ Dimension Mapper (5 pts)

### Lab 8 — CS4 Hybrid RAG & PE Workflows (67 points)
- ✅ Hybrid Retrieval with RRF Fusion (10 pts)
- ✅ HyDE Query Enhancement (7 pts)
- ✅ Score Justification Generator (12 pts)
- ✅ IC Meeting Prep Workflow (10 pts)
- ✅ Analyst Notes Collector (8 pts)
- ✅ Search API with filters (8 pts)
- ✅ Justification API endpoint (7 pts)
- ✅ Unit & integration tests (5 pts)

### Extensions (+10 bonus)
- ✅ Airflow Evidence Indexing DAG with pool control (+5 pts)
- ✅ Docker Compose with CS4 RAG API service (+5 pts)

### Testing Requirements
- ✅ ≥80% code coverage (97% achieved on scoring)
- ✅ All property tests pass with 500 examples
- ✅ Portfolio scores validated against expected ranges
- ✅ CS4 tests cover integration, RAG, workflows, and API
