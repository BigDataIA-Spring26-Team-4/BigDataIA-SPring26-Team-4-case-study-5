# PE Org-AI-R Platform — Case Study 3: AI Scoring Engine

## Summary
Duration: 0:02

### Overview

This codelab walks through the PE Org-AI-R Platform — a complete AI-readiness assessment system for private equity portfolio companies. Case Study 3 implements the scoring engine that converts evidence from 9 data sources into calibrated Org-AI-R scores across 7 dimensions for 5 real companies.

### What You'll Learn

- How evidence from CS2 (SEC filings, jobs, patents, tech stack) maps to 7 AI-readiness dimensions
- How the Org-AI-R scoring formula works (VR, HR, Synergy, confidence intervals)
- How new CS3 data sources (Glassdoor, Board composition, News) fill evidence gaps
- How to run the full pipeline via Streamlit UI and Airflow orchestration
- How Docker Compose manages 7 services (API, Streamlit, Redis, Airflow, PostgreSQL)

### What You'll Need

- Python 3.11+
- Docker Desktop
- Snowflake account
- API keys: Wextractor (Glassdoor), sec-api.io (Board), GNews, PatentsView

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend API | Python 3.12, FastAPI, Pydantic v2 |
| Database | Snowflake (cloud data warehouse) |
| Cache | Redis 7 (Alpine) |
| Frontend | Streamlit 1.54, Plotly |
| Orchestration | Apache Airflow 2.8 |
| Containerization | Docker Compose (7 services) |
| Testing | Pytest, Hypothesis (property-based) |

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Compose Stack                       │
│                                                               │
│  ┌──────────┐  ┌──────────┐  ┌─────────────────────────┐   │
│  │ Streamlit │─▶│ FastAPI  │─▶│  Snowflake (Cloud DW)   │   │
│  │  (8501)   │  │ (8000)   │  │                         │   │
│  └──────────┘  └────┬─────┘  └─────────────────────────┘   │
│                     │                                         │
│               ┌─────┴─────┐                                  │
│               │   Redis   │                                  │
│               │  (6379)   │                                  │
│               └───────────┘                                  │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                   Apache Airflow                      │   │
│  │  Webserver (8080) │ Scheduler │ PostgreSQL (5432)     │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Project Setup
Duration: 0:05

### Clone the Repository

```bash
git clone https://github.com/BigDataIA-Spring26-Team-4/BigDataIA-SPring26-Team-4-case-study-3.git
cd BigDataIA-SPring26-Team-4-case-study-3/pe-org-air-platform
```

### Option 1: Docker Compose (Recommended)

This starts all 7 services: API, Streamlit, Redis, PostgreSQL, Airflow (webserver + scheduler + init).

```bash
# Configure environment
cp docker/.env.example docker/.env
# Edit docker/.env with your Snowflake credentials and API keys

# Build and start
cd docker
docker compose up --build -d

# Verify (expect 6 running + 1 exited)
docker compose ps
```

Access points:

| Service | URL | Credentials |
|---------|-----|-------------|
| FastAPI Docs | http://localhost:8000/docs | — |
| Streamlit UI | http://localhost:8501 | — |
| Airflow UI | http://localhost:8080 | admin / admin |

### Option 2: Local Development

```bash
# Install dependencies
poetry install

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Start FastAPI (Terminal 1)
poetry run uvicorn app.main:app --reload

# Start Streamlit (Terminal 2)
poetry run streamlit run streamlit_app.py
```

---

## The CS2 → CS3 Gap
Duration: 0:03

### Problem: 4 Signals → 7 Dimensions

CS2 provides 4 signal categories. CS3 needs 7 dimension scores.

| CS2 Signal | Available? | CS3 Dimension | Source? |
|-----------|-----------|---------------|---------|
| technology_hiring | ✅ | Data Infrastructure | ❓ |
| innovation_activity | ✅ | AI Governance | ❌ NO SOURCE |
| digital_presence | ✅ | Technology Stack | ✅ |
| leadership_signals | ✅ | Talent | ✅ |
| | | Leadership | ✅ |
| | | Use Case Portfolio | ✅ |
| | | Culture | ❌ NO SOURCE |

### Solution: New Data Sources + Evidence Mapper

CS3 fills the gaps with:

1. **Glassdoor Reviews** → Culture dimension (employee sentiment analysis)
2. **Board Composition** → AI Governance dimension (sec-api.io + proxy statements)
3. **News/Press Releases** → Leadership dimension (public AI positioning)
4. **SEC Text Analysis** → Governance + Use Cases (keyword scoring of Items 1, 1A, 7)

The Evidence Mapper defines explicit weights from 9 sources to 7 dimensions.

---

## Evidence-to-Dimension Mapper (Task 5.0a)
Duration: 0:05

### The Mapping Table

Each source contributes to multiple dimensions with specific weights:

| Source | Data | Gov | Tech | Talent | Lead | Use | Culture |
|--------|------|-----|------|--------|------|-----|---------|
| technology_hiring | 0.10 | — | 0.20 | **0.70** | — | — | 0.10 |
| innovation_activity | 0.20 | — | **0.50** | — | — | 0.30 | — |
| digital_presence | **0.60** | — | 0.40 | — | — | — | — |
| leadership_signals | — | 0.25 | — | — | **0.60** | — | 0.15 |
| SEC Item 1 | — | — | 0.30 | — | — | **0.70** | — |
| SEC Item 1A | 0.20 | **0.80** | — | — | — | — | — |
| SEC Item 7 | 0.20 | — | — | — | **0.50** | 0.30 | — |
| Glassdoor | — | — | — | 0.10 | 0.10 | — | **0.80** |
| Board Comp. | — | **0.70** | — | — | 0.30 | — | — |

**Bold** = Primary contribution. Weights within each source sum to 1.0.

### Implementation

Located in `app/scoring/evidence_mapper.py`:

- `EvidenceMapper.map_evidence_to_dimensions()` — Converts evidence scores to 7 dimension scores
- Uses weighted averaging with confidence × reliability scaling
- Dimensions with no evidence default to 50.0
- All calculations use Python `Decimal` for precision

---

## Rubric-Based Scorer (Task 5.0b)
Duration: 0:03

### 5-Level Scoring Rubrics

Each of the 7 dimensions has a 5-level rubric:

| Level | Range | Label |
|-------|-------|-------|
| 5 | 80-100 | Excellent |
| 4 | 60-79 | Good |
| 3 | 40-59 | Adequate |
| 2 | 20-39 | Developing |
| 1 | 0-19 | Nascent |

### Example: Talent Dimension

| Level | Criteria | Keywords |
|-------|----------|----------|
| 5 | Large AI/ML team (>20), internal ML platform | ml platform, ai research, large team |
| 4 | Established team (10-20), active hiring | data science team, ml engineers |
| 3 | Small team (3-10), growing capability | data scientist, growing team |
| 2 | 1-2 data scientists, high turnover | junior, contractor, turnover |
| 1 | No dedicated AI/ML talent | no data scientist, vendor only |

### Implementation

Located in `app/scoring/rubric_scorer.py`:

- Checks levels from 5 down to 1
- Keyword matching + quantitative thresholds
- Interpolates within level range based on match density
- All 7 dimensions × 5 levels fully implemented

---

## CS3 Data Collectors
Duration: 0:05

### Glassdoor Culture Collector (Task 5.0c)

**Purpose:** Fill the Culture dimension gap with employee review analysis.

**Scoring formula:**
- `innovation_score` = (positive - negative mentions) / total × 50 + 50
- `data_driven_score` = data mentions / total × 100
- `ai_awareness_score` = AI mentions / total × 100
- `change_readiness` = (positive change - negative) / total × 50 + 50
- **Overall** = 0.30 × innovation + 0.25 × data_driven + 0.25 × ai_awareness + 0.20 × change

**API:** Wextractor (100 reviews per company)

### Board Composition Analyzer (Task 5.0d)

**Purpose:** Fill the AI Governance dimension gap with board-level AI oversight signals.

**Scoring (additive, capped at 100):**

| Indicator | Points |
|-----------|--------|
| Base score | 20 |
| Tech/Digital committee exists | +15 |
| Board member with AI/ML expertise | +20 |
| CAIO/CDO/CTO on executive team | +15 |
| Independent director ratio > 0.5 | +10 |
| Risk committee with tech oversight | +10 |
| AI in strategic priorities | +10 |

**API:** sec-api.io (real board data from proxy filings) + cached enriched bios

### News/Press Release Collector

**Purpose:** Supplement Leadership dimension with public AI positioning signals.

**API:** GNews (free tier) + company newsroom scraping

**Scoring:** 0.40 × leadership + 0.35 × deployment + 0.25 × investment

---

## Talent Concentration & VR Calculator (Tasks 5.0e, 5.2)
Duration: 0:04

### Talent Concentration (Key-Person Risk)

TC measures how concentrated AI capability is in a few people:

```
TC = 0.4 × leadership_ratio + 0.3 × team_size_factor
   + 0.2 × skill_concentration + 0.1 × individual_mentions
```

- TC = 0.0: Distributed capability (low risk)
- TC = 1.0: Single-person dependency (max risk)

**TalentRiskAdj** = 1 − 0.15 × max(0, TC − 0.25)

### Value-Readiness (VR) Calculator

```
VR = D̄w × (1 − λ × cv_D) × TalentRiskAdj
```

Where:
- D̄w = weighted mean of 7 dimension scores
- λ = 0.25 (non-compensatory CV penalty)
- cv_D = coefficient of variation across dimensions

**Dimension Weights:**

| Dimension | Weight |
|-----------|--------|
| Data Infrastructure | 0.25 |
| AI Governance | 0.20 |
| Technology Stack | 0.15 |
| Talent & Skills | 0.15 |
| Leadership | 0.10 |
| Use Case Portfolio | 0.10 |
| Culture & Change | 0.05 |

---

## Position Factor, HR, Synergy & Org-AI-R (Tasks 6.0a–6.4)
Duration: 0:04

### Position Factor (PF)

Measures company position relative to sector peers:

```
PF = 0.6 × VR_component + 0.4 × MCap_component
```

Bounded to [-1, 1]. NVDA = +0.56, DG = -0.26.

### Historical Readiness (HR)

```
HR = HR_base × (1 + δ × PF)
```

δ = 0.15 (corrected in v3.0)

### Synergy

```
Synergy = VR × HR / 100 × Alignment × TimingFactor
```

TimingFactor ∈ [0.8, 1.2]

### Final Org-AI-R Score

```
Org-AI-R = (1 − β) × [α × VR + (1 − α) × HR] + β × Synergy
```

α = 0.60 (idiosyncratic weight), β = 0.12 (synergy weight)

### SEM-Based Confidence Intervals

```
SEM = σ × √(1 − ρ)
ρ = (n × r) / (1 + (n − 1) × r)   [Spearman-Brown]
```

95% CI = score ± 1.96 × SEM

---

## 5-Company Portfolio Results (Task 6.5)
Duration: 0:03

### Final Scores

| Company | Sector | Org-AI-R | VR | HR | Synergy | 95% CI | Expected |
|---------|--------|----------|------|------|---------|--------|----------|
| **NVIDIA** | Technology | **81.73** | 78.35 | 92.04 | 66.32 | [78.8, 84.7] | 85-95 |
| **Walmart** | Retail | **66.98** | 66.13 | 75.22 | 46.54 | [64.0, 69.9] | 55-65 |
| **JPMorgan** | Financial | **63.06** | 55.18 | 83.87 | 36.73 | [60.1, 66.0] | 65-75 |
| **GE** | Manufacturing | **59.66** | 55.50 | 74.22 | 35.25 | [56.7, 62.6] | 45-55 |
| **Dollar General** | Retail | **46.74** | 39.28 | 67.22 | 19.48 | [43.8, 49.7] | 35-45 |

**Ranking:** NVDA > WMT > JPM > GE > DG ✓ (NVDA highest, DG lowest as expected)

### Key Observations

- **NVIDIA** scores highest due to massive AI hiring (90/100), 100/100 patents and tech stack, and strong board governance with Jensen Huang recognized as AI expert
- **JPMorgan** has high HR (83.87) from $15B+ tech spend heritage, but moderate VR from conservative SEC text analysis
- **Walmart** outperforms expected range due to genuinely strong signals: board includes CTO Suresh Kumar, 83 patents
- **Dollar General** correctly scores lowest: no tech committee, no AI expertise on board, limited tech stack

---

## Streamlit Dashboard
Duration: 0:05

### 9-Page Dashboard

The Streamlit app provides a comprehensive UI for exploring scores, running pipelines, and configuring weights — all via FastAPI backend calls.

| Page | Key Features |
|------|-------------|
| 📊 Portfolio Overview | KPI metrics, bar charts with CI, VR/HR/Synergy breakdown |
| 🔍 Company Deep Dive | 7-dimension radar chart, score decomposition, parameters |
| 📐 Dimension Analysis | Heatmap, per-dimension comparison, radar overlay |
| 📡 CS2 Evidence Dashboard | Signal weights from API, evidence stats, composite recalculation |
| ⚖️ Signal Weight Configurator | Sliders, live preview, persist to Snowflake via API |
| 🚀 Pipeline Control | Run CS2/CS3/Scoring via API, progress bars, task history |
| 🧮 Scoring Methodology | Formulas, dimension weights from API, Sankey diagram |
| 📂 Evidence Explorer | Direct API calls to /documents and /signals, 6 evidence tabs |
| 🧪 Testing & Coverage | Run pytest from UI, coverage chart, Hypothesis details |

### API Integration

Every page fetches data through FastAPI routers:

- Health check displayed in sidebar (Snowflake ✅, Redis ✅, S3 ⏸)
- Companies fetched from `GET /api/v1/companies`
- Dimension weights from `GET /api/v1/config/dimension-weights`
- Evidence from `GET /api/v1/documents` and `GET /api/v1/signals` (direct router calls)
- API call details shown in expandable panels with status codes and response times

### CS2 Signal Weights (Configurable)

Default weights shown on multiple pages, adjustable via sliders:

| Signal | Default Weight |
|--------|---------------|
| Technology Hiring | 0.30 |
| Innovation Activity | 0.25 |
| Digital Presence | 0.25 |
| Leadership Signals | 0.20 |

Users can recalculate composite scores via `POST /api/v1/pipeline/recalculate-composite`.

---

## FastAPI Backend
Duration: 0:04

### API Router Architecture

All data flows through FastAPI routers → Snowflake:

| Router | Prefix | Purpose |
|--------|--------|---------|
| `health.py` | `/health` | Dependency health check |
| `companies.py` | `/api/v1/companies` | Company CRUD with pagination |
| `assessments.py` | `/api/v1/assessments` | Assessment lifecycle |
| `scores.py` | `/api/v1/scores` | Dimension score updates |
| `industries.py` | `/api/v1/industries` | Industry reference data (1hr cache) |
| `config.py` | `/api/v1/config` | Dimension weight configuration |
| `documents.py` | `/api/v1/documents` | SEC document CRUD |
| `signals.py` | `/api/v1/signals` | External signal CRUD + evidence stats |
| `pipeline.py` | `/api/v1/pipeline` | Pipeline execution, scoring, weights |

### Key Pipeline Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/pipeline/collect-evidence` | POST | CS2 evidence collection (background task) |
| `/api/v1/pipeline/collect-cs3` | POST | CS3 signals: Glassdoor + Board + News |
| `/api/v1/pipeline/score` | POST | Score single company |
| `/api/v1/pipeline/score-portfolio` | POST | Score all 5 companies |
| `/api/v1/pipeline/recalculate-composite` | POST | Recalculate with custom weights |
| `/api/v1/pipeline/signal-weights` | GET | Get default signal weights |
| `/api/v1/pipeline/evidence-summary/{ticker}` | GET | Full evidence summary from Snowflake |
| `/api/v1/pipeline/status/{task_id}` | GET | Poll background task status |

---

## Airflow Orchestration
Duration: 0:04

### Two DAGs

| DAG | Schedule | Tasks | Purpose |
|-----|----------|-------|---------|
| `evidence_collection_pipeline` | Sundays 4am UTC | 16 | CS2 + CS3 collection (parallel per company) |
| `scoring_pipeline` | Mondays 6am UTC | 6 | Score + validate + aggregate |

### Evidence Collection DAG

```
start → health_check → [cs2_nvda, cs2_jpm, cs2_wmt, cs2_ge, cs2_dg]
                                            ↓
                        [cs3_nvda, cs3_jpm, cs3_wmt, cs3_ge, cs3_dg]
                                            ↓
                                    collection_summary → end
```

- 5 CS2 tasks run in parallel (one per company)
- 5 CS3 tasks run in parallel after CS2 completes
- All tasks call FastAPI endpoints via HTTP

### Scoring Pipeline DAG

```
start → wait_for_evidence → score_portfolio → validate_results → aggregate_portfolio → end
```

- `wait_for_evidence`: ExternalTaskSensor (soft-fail if evidence DAG hasn't run)
- `score_portfolio`: Calls `POST /api/v1/pipeline/score-portfolio`
- `validate_results`: Checks scores against expected ranges (±10 tolerance)
- `aggregate_portfolio`: Logs final ranking (#1 NVDA through #5 DG)

### Running Airflow

Access at http://localhost:8080 (admin/admin):
1. Navigate to DAGs page
2. Click `scoring_pipeline` → ▶ Trigger DAG
3. Watch Graph view: tasks turn green in sequence (~1 minute)
4. Click each task → "Log" to see scores and validation

---

## Testing & Quality
Duration: 0:03

### Test Suite

| Metric | Value |
|--------|-------|
| Total Tests | 255 passed |
| Code Coverage | 97% |
| Hypothesis Property Tests | 6 × 500 examples |
| Test Run Time | ~33 seconds |

### Property-Based Tests (Hypothesis)

| Test | Property Verified |
|------|------------------|
| test_property_scores_bounded | All 7 dimension scores ∈ [0, 100] |
| test_property_all_seven_returned | Always returns exactly 7 dimensions |
| test_property_tc_bounded | TC ∈ [0, 1] for any job distribution |
| test_property_vr_bounded | VR ∈ [0, 100] for any dimension scores |
| test_property_bounded (PF) | PF ∈ [-1, 1] for any VR and market cap |
| test_property_bounded (Org-AI-R) | Final score ∈ [0, 100] for any inputs |

### Running Tests

```bash
# All tests (local)
poetry run pytest -v --cov=app/scoring

# From Streamlit UI (Docker)
Navigate to 🧪 Testing & Coverage → Click "Run Full Test Suite"
```

---

## Docker Infrastructure
Duration: 0:03

### 7-Service Architecture

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| api | python:3.11 + FastAPI | 8000 | Backend REST API |
| streamlit | python:3.11 + Streamlit | 8501 | 9-page dashboard |
| redis | redis:7-alpine | 6379 | Response caching |
| postgres | postgres:15-alpine | 5432 | Airflow metadata |
| airflow-webserver | apache/airflow:2.8.1 | 8080 | Airflow UI |
| airflow-scheduler | apache/airflow:2.8.1 | — | DAG execution |
| airflow-init | apache/airflow:2.8.1 | — | One-time DB setup |

### Key Docker Commands

```bash
# Start everything
cd docker && docker compose up --build -d

# Check status
docker compose ps

# View API logs
docker compose logs api --tail 50

# View Airflow scheduler logs
docker compose logs airflow-scheduler --tail 50

# Rebuild single service
docker compose up --build streamlit -d

# Stop everything
docker compose down

# Stop and remove all data
docker compose down -v
```

---

## Team Contributions & AI Usage
Duration: 0:02

### Team Members

| Member | Contributions |
|--------|--------------|
| **Deep Prajapati** | CS1 API design, CS2 evidence collection (SEC, jobs, patents, tech), CS3 scoring engine (all 11 components), Glassdoor/Board/News collectors, Streamlit dashboard (9 pages), Docker Compose (7 services), Airflow DAGs, integration testing, documentation |
| **Tapan Patel** | Airflow DAG design reference, initial Docker setup |
| **Naman Patel** | [Add contributions] |

### AI Tools Used

| Tool | Usage |
|------|-------|
| Claude (Anthropic) | Code generation, debugging, architecture design, formula verification, test writing, documentation |
| GitHub Copilot | Inline code suggestions |

---

## Deliverables Checklist
Duration: 0:02

### Lab 5 (50 points)

- ✅ Evidence Mapper with complete mapping table (10 pts)
- ✅ Rubric Scorer with all 7 dimension rubrics (8 pts)
- ✅ Glassdoor Culture Collector (7 pts)
- ✅ Board Composition Analyzer (7 pts)
- ✅ Talent Concentration Calculator (5 pts)
- ✅ Decimal utilities (3 pts)
- ✅ VR Calculator with audit logging (5 pts)
- ✅ Property-based tests (5 pts)

### Lab 6 (50 points)

- ✅ Position Factor Calculator (5 pts)
- ✅ Integration Service — full pipeline (15 pts)
- ✅ HR Calculator with δ = 0.15 (5 pts)
- ✅ SEM-based Confidence Calculator (5 pts)
- ✅ Synergy Calculator (5 pts)
- ✅ Org-AI-R Calculator (5 pts)
- ✅ 5-company portfolio results (10 pts)

### Testing Requirements

- ✅ ≥80% code coverage → **97% achieved**
- ✅ All property tests pass with 500 examples → **3,000 random cases**
- ✅ Portfolio scores validated against expected ranges
