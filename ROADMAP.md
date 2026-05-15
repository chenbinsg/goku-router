# Goku-Router — Product Roadmap

> Current version: **v0.2** | Updated: 2026-05

This document compares the current implementation against 8 desired capabilities and maps each gap into a phased delivery plan.

---

## Current State vs Desired Features

| # | Feature | Current State | Gap | Readiness |
|---|---------|--------------|-----|-----------|
| 1 | **Internal / External Host Routing** | Provider adapter types exist (`mock`, `openai_compatible`). Fallback pair (primary → backup) modeled. | No `is_internal` flag. No vLLM/Ollama native adapter. No circuit breaker or health-heartbeat. Failed providers stay in candidate list. | 40% |
| 2 | **Smart Routing** (cost / context / cache) | Cost scoring, context-window filtering, workload classifier, prompt cache model — all coded. | Token counting uses `str.split()` (not tiktoken). Provider latency stats not updated from real traffic. No semantic cache. | 60% |
| 3 | **Security Controls** | Request-side keyword blocking, workspace-scoped guardrails, dry-run testing. | **No response filtering at all.** Only exact-string matching (no regex). No PII detection. No rate limiting. | 30% |
| 4 | **Self-Evolution** | Weight grid search, A/B experiment infra, log-based recalibration — all in `crud.py`. | Recalibration only fires on manual API call. No automatic trigger on drift. No rollback if new weights regress. | 50% |
| 5 | **Logs & Audit** | `RequestLog` (20+ fields including full `route_trace_json`), `AuditLog` for admin actions. | Audit log is write-only (no admin UI). No retention enforcement. No log signing. Sensitive data logged in plain text. | 50% |
| 6 | **Token Usage & Anomaly Detection** | Token aggregation by org/project, cost analysis, 3 hardcoded anomaly alerts (provider failure rate, latency, fallback rate). | Synthetic token counts from mock providers. Thresholds hardcoded, not per-tenant. No quota enforcement at request time. | 45% |
| 7 | **Billing** | Per-request cost formula coded. `BillingRecord` table defined. `/admin/billing/usage` endpoint exists. | `BillingRecord` is **never written to**. Budget (`quota_requests`) not enforced. No invoice generation. CSV export limited to 100 rows. | 25% |
| 8 | **Database & End-to-End** | Full request path works (auth → route → execute → log). SQLite auto-seeded on startup. | SQLite only (not production-ready). No DB health check endpoint. No schema versioning. Migration is ad-hoc `ALTER TABLE`. | 60% |

---

## Phase 0 — Foundation Fix `v0.3` *(2–3 weeks)*

**Goal:** Make everything that looks implemented actually work end-to-end with real providers.

### P0-1: Real Provider Execution

- Replace `str.split()` token counting with **tiktoken** (OpenAI) / **anthropic tokenizers**
- Populate `provider_reported_cost` from actual upstream API responses (already partially coded in `providers.py:262-265`)
- Enforce `quota_requests` on `RouterApiKey` during request validation (`require_api_key()`)
- Write a `BillingRecord` row for every completed request (model exists, zero writes today)

### P0-2: Database Production Readiness

- Switch default DB to **MySQL / PostgreSQL** (SQLite stays for dev only)
- Replace ad-hoc `ALTER TABLE` migration with **Alembic** versioned migrations
- Add `GET /health` with DB connectivity check and provider reachability probe
- Fix seed idempotency — seeding must be safe to run N times

### P0-3: Rate Limiting

- Per-API-key rate limiting via `slowapi` or Redis sliding window
- 429 response with `Retry-After` header
- Configurable limits per key (field already on `RouterApiKey`)

**Deliverable:** A running router that charges real token costs, enforces key quotas, and survives a restart without losing data.

---

## Phase 1 — Core Routing `v0.4` *(3–4 weeks)*

**Goal:** Deliver features 1 and 2 at production quality.

### 1.1: Internal / External Host Routing

**New fields on `Provider` model:**
```
host_type: Enum("internal", "external")   # vLLM, Ollama = internal; OpenAI, Anthropic = external
region: str                                # e.g., "jp-east-1", "us-west-2"
health_check_url: str                      # probe endpoint
health_check_interval_s: int = 30
```

**New `InternalAdapter`** in `services/providers.py`:
- Targets vLLM (`/v1/chat/completions`) and Ollama (`/api/chat`) natively
- Automatic base-URL discovery from env `PROVIDER_{NAME}_BASE_URL`
- Health heartbeat loop updates `Provider.health_status` every 30 s

**Circuit Breaker** (`services/circuit_breaker.py`):
- States: CLOSED → OPEN (after N failures) → HALF-OPEN (probe after cooldown)
- Failed providers excluded from `_resolve_candidates()` automatically
- Tripped circuits recorded in `route_trace_json`

**Routing preference:**
```
WorkspaceRouteDefault.prefer_internal = True  # route to internal first; fall back to external
```

### 1.2: Smart Routing Improvements

**Context-window-aware routing:**
- Count actual request tokens with tiktoken before resolving candidates
- Reject providers whose `max_input_tokens` < actual prompt token count (not just model catalog metadata)
- Add `token_count` to route trace

**Live latency tracking:**
- Update `Provider.avg_latency_ms` from each real request (exponential moving average)
- Surface P50/P95 latency per provider in `/admin/analytics/summary`

**Semantic prompt caching** (optional, toggled per workspace):
- Embed prompt with a lightweight model (e.g., `text-embedding-3-small`)
- Cosine similarity threshold configurable per workspace (default 0.97)
- Cache TTL configurable per workspace

**Deliverable:** Routing transparently prefers local (cheap, fast) models, falls back to external on failure or context overflow, with real latency data driving scoring.

---

## Phase 2 — Security `v0.5` *(3–4 weeks)*

**Goal:** Feature 3 — full request AND response safety pipeline.

### 2.1: Request Filtering (enhance existing)

- Upgrade from exact-string to **regex pattern matching** on `blocked_words`
- Support named categories: `pii`, `profanity`, `competitor`, `internal_code` with built-in default patterns
- Per-workspace pattern inheritance (org → workspace → project, strictest wins)
- Return structured rejection: `{ "error": "policy_violation", "category": "pii", "matched": "<redacted>" }`

### 2.2: Response Filtering (net new)

All provider completions pass through a **ResponseSafetyPipeline** before returning to the client:

```
Provider response
     ↓
[Pattern scan]  — blocked_words / regex match on completion text
     ↓
[PII detector]  — Presidio (phone, email, SSN, credit card, names)
     ↓
[Custom rules]  — workspace-level deny patterns
     ↓
Pass / Block / Redact
```

- **Block mode**: 451 status, no content returned, audit log entry
- **Redact mode**: Replace matched spans with `[REDACTED]`, return partial response
- Workspace config selects mode per category

### 2.3: PII Detection

- Integrate **Microsoft Presidio** (Python library, no external service required)
- Entities: `PHONE_NUMBER`, `EMAIL_ADDRESS`, `CREDIT_CARD`, `PERSON`, `ID_NUMBER`
- Configurable per workspace: detect only, redact, or block
- PII hit events recorded in `AuditLog` without storing the original value

### 2.4: Sensitive Data in Logs

- Add `log_prompt: bool` and `log_completion: bool` flags per workspace (`WorkspaceGuardrailConfig`)
- When disabled, `RequestLog` stores `prompt_sha256` and `completion_sha256` instead of raw text
- API keys hashed with bcrypt before storage (already partially done)

### 2.5: Real-Time Audit Alerts

- Webhook delivery on high-severity audit events (configurable URL per org)
- Event types: guardrail block, circuit breaker trip, quota exhaustion, provider error spike
- Retry with exponential backoff (3 attempts), dead-letter to `NotificationRecord`

**Deliverable:** Every request and response scanned; PII never stored in plain logs; audit webhooks fire within seconds of a policy event.

---

## Phase 3 — Observability & Billing `v0.6` *(3–4 weeks)*

**Goal:** Features 5, 6, 7 — real billing pipeline, configurable anomaly detection, external log export.

### 3.1: Billing Pipeline

- Write `BillingRecord` on every completed request (today it's never written)
- Fields: `org_id`, `project_id`, `api_key_id`, `model`, `provider`, `input_tokens`, `output_tokens`, `cached_tokens`, `cost_usd`, `upstream_cost_usd`, timestamp
- **Budget enforcement**: Check cumulative `BillingRecord` spend vs `RouterApiKey.quota_spend_usd` before routing; return 429 if exhausted
- **Monthly rollup job** (APScheduler): aggregate `BillingRecord` into `MonthlyBillingSummary` per org
- **Invoice export**: `GET /admin/billing/invoice?org_id=&month=` → PDF or CSV line items
- **Chargeback report**: split shared-gateway costs across departments by `project_id`

### 3.2: Token Usage Dashboard

- `/admin/analytics/token-usage` — daily/weekly/monthly token burn by model, provider, org
- **Quota progress bars**: prompt tokens used / quota_tokens_monthly per API key
- **Cost trend**: 7-day rolling cost vs prior period (week-over-week %)
- Top 10 most expensive requests (by cost) per org

### 3.3: Configurable Anomaly Detection

Replace hardcoded thresholds with per-tenant configuration:

```
AnomalyThresholdConfig (per org):
  provider_failure_rate_pct: float = 25.0
  provider_latency_ms: float = 600.0
  workspace_fallback_rate_pct: float = 30.0
  cost_spike_multiplier: float = 3.0   # alert if cost 3× prior day avg
  token_spike_multiplier: float = 2.5
```

- **Baseline calculation**: 7-day rolling average per provider/workspace (not fixed threshold)
- **Cost spike detection**: alert when hourly spend > `cost_spike_multiplier × 7d_hourly_avg`
- **Token anomaly**: alert when a single request consumes > 10% of daily quota

### 3.4: Log Export

- **Structured log streaming** to stdout (JSON Lines format, for log aggregators: Fluentd, Logstash, Vector)
- Optional: export `RequestLog` rows to S3/GCS on a configurable schedule
- **Log retention enforcement**: delete `RequestLog` rows older than `retention_days` (set per workspace in `WorkspaceGuardrailConfig`)
- **Log search API**: `GET /admin/logs?q=<text>&model=&provider=&status=&from=&to=` with full-text search on `route_trace_json`

**Deliverable:** Finance team can pull invoices without engineering help. On-call gets paged when a provider spikes. Logs auto-expire per contractual retention period.

---

## Phase 4 — Self-Evolution `v0.7` *(4–6 weeks)*

**Goal:** Feature 4 — the router improves itself from production traffic without human intervention.

### 4.1: Automatic Recalibration Trigger

Today `recalibrate_route_scoring_profile_from_logs()` must be called manually. Phase 4 automates it:

- **Drift monitor job** (runs every 6 hours via APScheduler):
  - Computes current routing weight vs `DEFAULT_ROUTE_SCORING_WEIGHTS`
  - Computes live signal deviations: fallback rate, cache hit rate, provider success rate
  - If drift score > threshold → trigger recalibration automatically
- **Recalibration guard**: recalibration only fires if ≥ 500 new `RequestLog` rows since last run
- Write recalibration event to `AuditLog` with before/after weight delta

### 4.2: Statistical A/B Experiment Lifecycle

Automate the full experiment loop:

1. **Auto-launch**: when recalibration produces weights diverging > 10% from control, create `RouteScoringExperiment` automatically (10% challenger traffic)
2. **Statistical significance check** (runs nightly): compare challenger vs control on success rate, avg cost, fallback rate using two-proportion z-test
3. **Auto-promote**: if challenger is statistically better (p < 0.05) and ran for ≥ 7 days → promote to active profile
4. **Auto-rollback**: if challenger is significantly worse → stop experiment, revert, alert

### 4.3: Provider Quality Learning

- After each real provider response, update a `ProviderQualityScore` per `(provider, workload_class)`:
  - Schema validity rate (for structured_extraction)
  - Tool call success rate (for tool_use)
  - Subjective proxy: completion length vs prompt complexity ratio
- Feed `ProviderQualityScore` into route scoring (replaces mock capability tags with measured data)

### 4.4: Workload Classifier Upgrade

Replace rule-based keyword classifier with a **lightweight ML classifier**:

- Train on request shape features: message count, tool presence, response_format, system prompt keywords, token count
- Target labels: the 7 workload classes already defined (`chat_general`, `tool_use`, `structured_extraction`, etc.)
- Model: logistic regression or gradient boosting (< 1 MB, runs in-process, no GPU needed)
- Retrain monthly from `RequestLog` labels confirmed by routing outcomes

### 4.5: Feedback Loop API

Allow downstream systems to push quality signals back:

```
POST /v1/feedback
{
  "request_id": "...",
  "rating": 1–5,          # user thumbs up/down mapped to 1/5
  "success": true/false,  # task-level success from the calling app
  "notes": "..."
}
```

- Feedback stored on `RequestLog.user_feedback_score`
- Used in A/B experiment evaluation and provider quality scoring
- Weighted more heavily than system signals (success/failure)

**Deliverable:** The routing model improves weekly from production traffic. A/B tests run and conclude without human involvement. Provider quality scores reflect real measured performance.

---

## Summary Timeline

```
v0.3  Foundation Fix         ████░░░░░░░░░░░░░░░░  2–3 weeks
v0.4  Core Routing           ████████░░░░░░░░░░░░  3–4 weeks
v0.5  Security               ████████████░░░░░░░░  3–4 weeks
v0.6  Observability/Billing  ████████████████░░░░  3–4 weeks
v0.7  Self-Evolution         ████████████████████  4–6 weeks
                             ─────────────────────
Total                        ~18–24 weeks to full feature parity
```

---

## Priority Matrix

| Feature | Business Value | Implementation Risk | Ship in |
|---------|---------------|---------------------|---------|
| Real token counting | High (billing accuracy) | Low | v0.3 |
| BillingRecord writes | High (revenue) | Low | v0.3 |
| Quota enforcement | High (cost control) | Low | v0.3 |
| MySQL + Alembic | High (production stability) | Medium | v0.3 |
| Internal host routing | High (cost reduction) | Medium | v0.4 |
| Circuit breaker | High (reliability) | Medium | v0.4 |
| Response filtering | High (compliance) | Medium | v0.5 |
| PII detection | High (compliance) | Low (Presidio OSS) | v0.5 |
| Configurable anomaly thresholds | Medium | Low | v0.6 |
| Invoice generation | Medium (enterprise sales) | Low | v0.6 |
| Log export to S3/aggregators | Medium | Medium | v0.6 |
| Auto-recalibration trigger | Medium (OpEx reduction) | Medium | v0.7 |
| A/B auto-promote/rollback | Medium | High | v0.7 |
| ML workload classifier | Low | High | v0.7 |
| Semantic prompt caching | Medium | High | v0.4+ |

---

## What Does NOT Need Building

The following are already well-implemented and should not be re-architected:

- **Route scoring formula** — workload-class weight vectors are solid; just needs real data feeding them
- **Policy hierarchy** (org → workspace → project → key) — data model is correct
- **A/B experiment bucketing** — deterministic hash split is correct; needs lifecycle automation only
- **Audit log writes** — comprehensive coverage across all admin actions; needs UI and export
- **Prompt cache data model** — `PromptCacheEntry` is correct; needs semantic matching upgrade
- **Workload classification logic** — rule-based classifier works for v0.4; ML upgrade is v0.7
- **Route decision trace** — `route_trace_json` format is excellent; keep it

---

*Goku-Router Roadmap — v0.2 → v0.7 | © Chuck 2026*
