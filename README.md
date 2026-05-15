# Goku-Router

> **Version v0.2** | An enterprise-grade AI traffic control plane

Goku-Router is a multi-model LLM gateway that routes requests intelligently across providers — not just by availability, but by workload class, policy, cost, and measured quality. It offers an OpenAI-compatible API surface so existing clients work without modification, while the routing layer makes governance-aware decisions that OpenRouter alone cannot.

---

## Why Goku-Router

| Capability | Goku-Router | OpenRouter |
|------------|-------------|------------|
| OpenAI-compatible endpoint | ✅ | ✅ |
| Multi-provider fallback | ✅ | ✅ |
| Workload-class-aware routing | ✅ | ❌ |
| Policy engine (budget / data / capability) | ✅ | Partial |
| Eval-driven routing decisions | ✅ | ❌ |
| Zero-data-retention (ZDR) enforcement | ✅ | ❌ |
| Full route decision trace per request | ✅ | ❌ |
| On-prem / private-region deployable | ✅ | ❌ |

---

## Architecture

```
Client (OpenAI-compatible)
        │
        ▼
  Goku-Router API (FastAPI)
  ├── Auth & API Key validation
  ├── Policy Engine  ─── enforces budget / data / capability rules
  ├── Task Classifier ── detects workload class from request shape
  ├── Route Scorer   ─── multi-objective scoring (quality, cost, latency)
  │       └── weights tuned per workload class
  ├── Provider Adapters
  │       ├── OpenAI-compatible
  │       └── Mock (testing / schema repair)
  ├── Response Healer ── repairs malformed structured outputs
  └── Request Logger  ── full route_trace_json per request
        │
   ┌────┴──────────────┐
   │ SQLAlchemy ORM    │
   │ MySQL (prod)      │
   │ SQLite (dev)      │
   └───────────────────┘
```

**Frontend**: React 18 + Ant Design admin console for provider management, routing rules, API keys, billing, and logs.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API server | FastAPI + Uvicorn |
| ORM / DB | SQLAlchemy 2.0, MySQL (prod) / SQLite (dev) |
| Auth | Python-Jose (JWT) + bcrypt |
| HTTP client | httpx |
| Frontend | React 18, Vite, Ant Design 5, TypeScript |

---

## Key Features

### Intelligent Routing

Requests are scored across candidate providers using workload-specific weight vectors:

| Workload class | Quality weight | Latency weight | Cost weight |
|----------------|---------------|---------------|------------|
| `tool_use` | 0.50 | 0.30 | 0.20 |
| `structured_extraction` | 0.35 | 0.15 | 0.50 |
| `long_context` | 0.20 | 0.10 | 0.70 |
| `chat_general` | 0.30 | 0.25 | 0.45 |
| `chat_reasoning` | 0.30 | 0.25 | 0.45 |

Routing strategies available: `static_primary_backup`, `cheapest_provider`, `fastest_provider`, `openrouter_like_auto`, `current_production_policy`.

### Policy Engine

Policies are enforced in a hierarchy: **Org → Workspace → Project → API Key → Request**.

| Policy type | What it controls |
|-------------|-----------------|
| Budget | Spend limits, reset intervals, BYOK cost counting |
| Model | Allow/denylist, context window caps |
| Provider | Provider restrictions, regional constraints |
| Data | ZDR requirements, retention modes, export controls |
| Capability | Tool calling, structured outputs, multimodal access |
| Safety | Blocked words, regex filters, tool denylist |

### Response Healing

When a provider returns malformed structured output:
- **json_object** — wraps response in `{"answer": ..., "provider": ...}`
- **json_schema** — attempts repair, generates a schema-valid replacement

### Route Decision Transparency

Every request records a `route_trace_json` capturing the full decision path: candidate providers, acceptance/rejection reasons, selected provider, fallback path, cost and latency predictions.

### Eval Harness

Routing changes are validated against benchmark datasets before deployment — not by heuristics alone.

```bash
# Run eval against all routing strategies
python backend/evals/run_eval.py --dataset evals/datasets/customer_support_pack.json

# Replay against a specific strategy
python backend/app/eval_runner.py --strategy cheapest_provider
```

Included datasets: `sample_workloads`, `customer_support`, `sales_ops_agent`, `finance_compliance`.

---

## Quick Start

### Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.11+ |
| Node.js | 18+ |
| MySQL | 8.0+ (prod) or SQLite (dev, default) |

### 1. Backend

```bash
cd /path/to/Goku-Router

python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

cp backend/.env.example .env
# Edit .env — set DATABASE_URL, SECRET_KEY, provider API keys

./start.sh
```

Backend runs at **http://localhost:8000** — Swagger docs at `/docs`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev     # http://localhost:5173 (dev)
npm run build   # production build
```

Admin console runs at **http://localhost:5159** (served via `scripts/serve_frontend.py`).

### 3. Environment Variables

```ini
# Required
DATABASE_URL=mysql+pymysql://user:pass@localhost:3306/goku_router
SECRET_KEY=<random-32-char-hex>

# Optional — provider runtime config
# Format: PROVIDER_{NORMALIZED_NAME}_{BASE_URL|API_KEY}
PROVIDER_OPENAI_BASE_URL=https://api.openai.com/v1
PROVIDER_OPENAI_API_KEY=sk-...
PROVIDER_ANTHROPIC_BASE_URL=https://api.anthropic.com
PROVIDER_ANTHROPIC_API_KEY=sk-ant-...

# Router API keys (comma-separated, for client auth)
ROUTER_API_KEYS=key1,key2
```

---

## API

The gateway exposes an **OpenAI-compatible** interface — drop in your existing `base_url`:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="your-router-api-key",
)

response = client.chat.completions.create(
    model="gpt-4o",           # resolved by route rules
    messages=[{"role": "user", "content": "Hello"}],
)
```

### Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/chat/completions` | Chat completions (streaming supported) |
| POST | `/v1/embeddings` | Embeddings |
| GET | `/v1/models` | Available model catalog |
| GET/POST | `/admin/providers` | Provider registry |
| GET/POST | `/admin/models` | Model catalog |
| GET/POST | `/admin/routes` | Route rules (primary/backup pairs) |
| GET/POST | `/admin/router-api-keys` | API key management |
| PUT | `/admin/guardrails` | Global guardrail config |
| POST | `/admin/guardrails/dry-run` | Test policy eligibility |
| GET | `/admin/billing/usage` | Usage by org/project/environment |
| GET | `/admin/logs` | Request logs |
| POST | `/admin/router-scoring/train` | Train route scoring profile |
| POST | `/admin/router-scoring/experiments` | A/B experiment setup |

Full interactive docs: `http://localhost:8000/docs`

---

## Admin Console (Frontend)

| Page | Purpose |
|------|---------|
| Dashboard | System overview — request rates, provider health, cost |
| Providers | Register and test upstream LLM providers |
| Models | Map logical model names to provider-specific names |
| Routing | Configure primary/backup route rules per model |
| API Keys | Issue, rotate, and expire client API keys |
| Billing | Cost tracking and CSV export |
| Logs | Request log viewer with filtering |
| Security | Org isolation and data controls |

---

## Development

```bash
# Run tests
PYTHONPATH=backend pytest backend/tests/ -v

# Run a single test
PYTHONPATH=backend pytest backend/tests/test_gateway.py -v

# Lint
ruff check backend/app/

# DB migrations (Alembic)
cd backend
alembic upgrade head
alembic revision --autogenerate -m "describe change"
```

---

## Roadmap

| Phase | Focus | Timeline |
|-------|-------|---------|
| **1** | OpenRouter parity+ — full OpenAI normalization, structured output repair, prompt caching, route trace | 4–6 weeks |
| **2** | Eval-driven routing — capability registry, multi-objective scorer, `router/auto` v2, per-customer learned policies | 6–8 weeks |
| **3** | Enterprise control plane — full tenancy, policy engine enforcement, ZDR-aware routing, audit workflows | 6–10 weeks |
| **4** | Beyond OpenRouter — route simulator, A/B testing, agent-aware routing, SLA reporting | 8–12 weeks |

See [`Deepwater_Roadmap.md`](Deepwater_Roadmap.md), [`Policy_Engine_PRD.md`](Policy_Engine_PRD.md), and [`Routing_Eval_Spec.md`](Routing_Eval_Spec.md) for detailed specs.

---

## Project Structure

```
Goku-Router/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, all route handlers
│   │   ├── models.py            # SQLAlchemy ORM (Provider, RouteRule, Policy, ...)
│   │   ├── crud.py              # Business logic and route scoring
│   │   ├── config.py            # Pydantic settings, env var loading
│   │   ├── eval_runner.py       # Routing strategy benchmarking
│   │   └── services/
│   │       └── providers.py     # Provider adapters (OpenAI-compatible, mock)
│   ├── evals/
│   │   ├── run_eval.py          # Eval CLI entry point
│   │   └── datasets/            # Benchmark workload packs
│   └── tests/                   # pytest suite
├── frontend/
│   └── src/
│       ├── pages/               # 14 admin + API consumer pages
│       ├── api/                 # Axios API client wrappers
│       └── types/               # TypeScript type definitions
├── database/
│   └── init.sql                 # MySQL schema for fresh installs
├── scripts/                     # Release build and smoke-check scripts
├── start.sh / stop.sh           # Local service lifecycle
└── VERSION                      # Current version (v0.2)
```

---

*Goku-Router v0.2 — AI Traffic Control Plane*
