# Goku-Router — Product Roadmap

> Current version: **v1.3.0** | Updated: 2026-05

This document compares the current implementation against 8 desired capabilities and maps each gap into a phased delivery plan.

---

## Feature Readiness

| # | Feature | Before | After v1.0.0–v1.1.0 | Readiness |
|---|---------|--------|-----------------|-----------|
| 1 | **Internal / External Host Routing** | No `host_type` flag. No circuit breaker. Failed providers stay in candidate list. | ✅ `host_type` / `region` on Provider. Circuit breaker (CLOSED/OPEN/HALF_OPEN). Internal providers use shorter timeout. | **75%** |
| 2 | **Smart Routing** (cost / context / cache) | Token counting used `str.split()`. Latency stats never updated from real traffic. | ✅ tiktoken real token counting. Live latency EMA updated after every call. Cost computed from actual tokens. | **80%** |
| 3 | **Security Controls** | Request-side keyword blocking only. No response filtering. No PII detection. No regex. | ✅ `safety.py`: request + response filtering. Regex patterns. PII redaction (6 built-in patterns). `log_prompt` / `log_completion` flags. | **70%** |
| 4 | **Self-Evolution** | Recalibration only on manual API call. No automatic trigger. No rollback. | ✅ Drift monitor job (every 6h): auto-recalibrate if ≥ 500 new logs + drift > 10%. Auto-launch A/B. Nightly z-test → auto-promote/rollback. ProviderQualityScore feeds into route scoring. | **80%** |
| 5 | **Logs & Audit** | Audit log write-only. Sensitive data in plain text. No retention enforcement. | ✅ `log_prompt` / `log_completion` flags. Audit log on all guardrail events. ✅ Log retention job (daily 02:00 UTC). Log search API `/admin/logs`. | **75%** |
| 6 | **Token Usage & Anomaly Detection** | Synthetic token counts. Thresholds hardcoded. Quota never enforced. | ✅ Real token counts from tiktoken. Configurable `AnomalyThresholdConfig` per org. Hourly anomaly sweep job. Token usage dashboard `/admin/analytics/token-usage`. | **80%** |
| 7 | **Billing** | `BillingRecord` never written. No spend tracking. No quota enforcement. | ✅ `BillingRecord` written on every request. Monthly rollup job → `MonthlyBillingSummary`. Invoice export (JSON + CSV) `/admin/billing/invoice`. | **80%** |
| 8 | **Database & End-to-End** | SQLite only. No DB health check. No schema versioning. | ✅ `/health` checks DB connectivity + circuit breaker states. `ensure_schema()` migrations extended for all new columns. | **70%** |

---

## ✅ Phase 0 — Foundation Fix `v1.0.0` — **SHIPPED**

### Completed
- ✅ **Real token counting** — `services/token_counter.py` using tiktoken; falls back to word-count if not installed
- ✅ **BillingRecord writes** — `_write_billing_record()` called on every successful request and cache hit; fields: `request_id`, `model`, `provider`, `tokens`, `cost_usd`, `upstream_cost_usd`, `cache_hit`, `fallback_used`
- ✅ **Quota enforcement** — `_check_quota()` checks `quota_requests`, `quota_spend_usd`, `expires_at` before routing; returns HTTP 429
- ✅ **Spend tracking** — `RouterApiKey.spend_usd` incremented after every request
- ✅ **DB health check** — `GET /health` now queries `SELECT 1` and reports circuit breaker states
- ✅ **Schema migrations** — `ensure_schema()` extended with all new v1.0.0–v1.1.0 columns

### Remaining (v1.2.0)
- ⬜ MySQL / Alembic versioned migrations (SQLite still default for dev)
- ⬜ Monthly billing rollup job
- ⬜ Invoice export endpoint

---

## ✅ Phase 1 — Core Routing `v1.0.1` — **SHIPPED**

### Completed
- ✅ **`host_type` field** — `Provider.host_type` (`internal` / `external`) + `region` field
- ✅ **Circuit breaker** — `services/circuit_breaker.py`; CLOSED → OPEN (5 failures) → HALF_OPEN (60s cooldown); thread-safe singleton
- ✅ **Circuit breaker integrated in routing** — `execute_chat_completion()` checks `circuit_breakers.is_available()` before calling provider; records success/failure after each call
- ✅ **Live latency EMA** — `Provider.avg_latency_ms` updated via exponential moving average (α=0.1) after every real call
- ✅ **Internal provider timeout** — 15s for `host_type=internal`, 30s for external
- ✅ **Admin endpoints** — `GET /admin/circuit-breakers` (state overview), `POST /admin/circuit-breakers/{name}/reset` (manual reset)

### Remaining (v1.0.1+)
- ⬜ `WorkspaceRouteDefault.prefer_internal` flag — explicit preference to route internal-first
- ⬜ Health heartbeat loop — background job probing internal provider `/health` every 30s
- ⬜ Semantic prompt caching (embedding-based similarity)

---

## ✅ Phase 2 — Security `v1.1.0` — **SHIPPED**

### Completed
- ✅ **`services/safety.py`** — unified request + response safety pipeline
- ✅ **Request filtering** — blocked words (exact, case-insensitive) + regex patterns; returns structured `SafetyViolation`
- ✅ **Response filtering** — all provider completions pass through `scan_response()` before returning to client
- ✅ **PII detection & redaction** — 6 built-in regex patterns: email, JP phone, US phone, credit card, US SSN, JP My Number; redacts in-place
- ✅ **Block vs Redact modes** — hard block for keyword/regex hits; soft redact for PII (response still returned with spans replaced)
- ✅ **New guardrail fields** — `blocked_response_words`, `regex_patterns`, `response_regex_patterns`, `detect_pii`, `log_prompt`, `log_completion` on `WorkspaceGuardrailConfig`
- ✅ **Audit on response block** — every blocked response writes to `AuditLog`
- ✅ **Feedback endpoint** — `POST /v1/feedback` accepts `rating` (1–5), `success` (bool), `notes`; stored in `route_trace_json` for future recalibration

### Remaining (v1.1.0+)
- ⬜ Audit webhook — push high-severity events to configurable org webhook URL
- ⬜ Named PII categories with per-workspace block/redact/allow config
- ⬜ Microsoft Presidio integration (replaces regex patterns with ML-based NER)

---

## ✅ Phase 3 — Observability & Billing `v1.2.0` — **SHIPPED**

**Goal:** Features 5, 6, 7 — full billing pipeline, configurable anomaly detection, log export.

### 3.1: Billing Pipeline

- ✅ **Monthly rollup job** (APScheduler) — `rollup_monthly_billing()` runs 1st of each month 01:00 UTC; aggregates `BillingRecord` → `MonthlyBillingSummary` by (org, project, model, provider)
- ✅ **Invoice export** — `GET /admin/billing/invoice?org_id=&month=` + `GET /admin/billing/invoice/export` (CSV); falls back to live aggregation mid-month
- ✅ **Monthly summaries list** — `GET /admin/billing/summaries` — browse pre-rolled rollups
- ⬜ **Chargeback report** — split shared gateway costs by `project_id` (v1.3.0)
- ⬜ **Paginated billing export** — remove 100-row limit from CSV export (v1.3.0)

### 3.2: Token Usage Dashboard

- ✅ `/admin/analytics/token-usage` — daily/weekly/monthly token burn by model, provider, org
- ✅ Quota progress per API key (used / limit)
- ✅ Cost trend — week-over-week % change
- ✅ Top 10 most expensive requests per org

### 3.3: Configurable Anomaly Detection

- ✅ `AnomalyThresholdConfig` model — per-org configurable thresholds (failure rate, latency, cost multiplier, token multiplier, rolling window)
- ✅ `GET/PUT /admin/anomaly-thresholds` — CRUD for threshold configs
- ✅ Hourly `run_anomaly_sweep()` job — reads live thresholds, detects provider failure spikes, latency spikes, cost spikes; writes `NotificationRecord`
- ✅ 7-day rolling baseline for cost spike detection

### 3.4: Log Export & Retention

- ✅ **Log retention job** — `enforce_log_retention()` runs daily 02:00 UTC; deletes `RequestLog` rows older than `LOG_RETENTION_DAYS` (default 90)
- ✅ **Log search API** — `GET /admin/logs?q=&model=&provider=&from=&to=&org_id=` with pagination
- ✅ **Manual retention trigger** — `POST /admin/logs/enforce-retention`
- ⬜ Structured JSON Lines to stdout (Fluentd/Logstash) — v1.3.0
- ⬜ Optional S3/GCS export — v1.3.0

**Deliverable:** Finance can pull invoices without engineering. On-call gets paged on provider spikes. Logs auto-expire per retention policy. ✅ **DONE**

---

## ✅ Phase 4 — Self-Evolution `v1.3.0` — **SHIPPED**

**Goal:** Feature 4 — router improves itself from production traffic without human intervention.

### 4.1: Automatic Recalibration Trigger

- ✅ **Drift monitor job** (APScheduler, every 6h): updates `ProviderQualityScore`, then calls `run_drift_monitor()` which auto-recalibrates when drift exceeds threshold
- ✅ **Recalibration guard**: only fires if ≥ 500 new `RequestLog` rows since last run
- ✅ **`RecalibrationEvent`** audit table: records trigger type, samples used, weight deltas (JSON), experiment name if auto-launched
- ✅ **`GET /admin/recalibration-events`** — audit trail API
- ✅ **`POST /admin/drift-monitor/run`** — manual trigger with configurable threshold

### 4.2: Statistical A/B Experiment Lifecycle

- ✅ **Auto-launch**: drift monitor creates `RouteScoringExperiment` at 10% traffic when weight delta > 10%; supersedes any running experiment
- ✅ **Nightly significance check** (03:00 UTC): two-proportion z-test on success rate across control/challenger buckets; user feedback weighted 2× vs system signals
- ✅ **Auto-promote**: promotes challenger profile if p < 0.05 and ran ≥ 7 days (writes AuditLog)
- ✅ **Auto-rollback**: stops experiment + writes NotificationRecord alert if challenger significantly worse
- ✅ **`POST /admin/router-scoring/ab-check`** — manual significance check trigger

### 4.3: Provider Quality Learning

- ✅ `ProviderQualityScore` model — per (provider, workload_class): success rate, schema validity rate, tool call success rate, avg latency, avg cost, composite quality score
- ✅ Quality score multiplied into `_provider_route_score()` — low-quality providers are penalised automatically
- ✅ `GET /admin/provider-quality-scores` — browse all scores
- ✅ `POST /admin/provider-quality-scores/refresh` — manual recompute
- ✅ Updated every 6h by drift monitor job

### 4.4: Workload Classifier Upgrade

- ⬜ Lightweight ML classifier (logistic regression) — v1.4.0
- ⬜ Monthly retrain from `RequestLog` labels — v1.4.0
- (Current rule-based classifier performs well; ML upgrade deferred)

### 4.5: Feedback Loop Completion

- ✅ `POST /v1/feedback` — endpoint live, data stored in `route_trace_json`
- ✅ User feedback score (1–5 rating) weighted 2× in A/B significance check (`feedback_boost`)
- ✅ Feedback delta applied to challenger success rate in z-test evaluation

**Deliverable:** Routing model auto-improves every 6h from traffic. A/B tests run and conclude automatically. Provider quality scores penalise underperformers. ✅ **DONE**

---

## Progress Summary

```
v1.0.0  Foundation Fix         ████████████████████  ✅ DONE
v1.0.1  Core Routing           ████████████████░░░░  ✅ DONE (85%)
v1.1.0  Security               ██████████████░░░░░░  ✅ DONE (75%)
v1.2.0  Observability/Billing  ██████████████████░░  ✅ DONE (90%)
v1.3.0  Self-Evolution         ████████████████░░░░  ✅ DONE (80%)
                             ─────────────────────
Remaining                    ~2–4 weeks to full feature parity (ML classifier, S3 export)
```

---

## What Does NOT Need Building

The following are already well-implemented and should not be re-architected:

- **Route scoring formula** — workload-class weight vectors are solid; just needs real data feeding them
- **Policy hierarchy** (org → workspace → project → key) — data model is correct
- **A/B experiment bucketing** — deterministic hash split is correct; needs lifecycle automation only
- **Audit log writes** — comprehensive coverage across all admin actions; needs UI and export
- **Prompt cache data model** — `PromptCacheEntry` is correct; needs semantic matching upgrade
- **Workload classification logic** — rule-based classifier works for now; ML upgrade is v1.3.0
- **Route decision trace** — `route_trace_json` format is excellent; keep it

---

*Goku-Router Roadmap — v1.3.0 | © Chuck 2026*
