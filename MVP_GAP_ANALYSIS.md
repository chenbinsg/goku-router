# Router MVP Gap Analysis

## Summary

This codebase is not yet a production-ready OpenSwitch-style AI gateway. It is closer to a product prototype with a partial frontend shell and placeholder backend endpoints.

The biggest issue is not missing polish. The main issue is that the core value chain is still incomplete:

- No real provider integration
- No routing engine
- No fallback or retry behavior
- No authentication or tenant isolation
- No usable billing or BYOK implementation
- No reliable test or deployment baseline

Given the current state, the recommended goal is to move from "prototype UI plus API shell" to "working MVP gateway" before adding advanced enterprise features.

## Current State Assessment

### 1. Backend is mostly a stub

The API surface exists, but the business logic is placeholder-only.

- `/v1/chat/completions` returns a fake completion
- `/v1/embeddings` returns a fake embedding
- `/v1/models` returns a hard-coded model list
- `/admin/billing/export` returns a fake CSV URL

Relevant files:

- [backend/app/crud.py](/Users/chenbin/router/backend/app/crud.py:4)
- [backend/app/main.py](/Users/chenbin/router/backend/app/main.py:31)

Impact:

- The product cannot yet demonstrate real model switching
- No benchmark can be run against OpenRouter, Portkey, or LiteLLM
- Frontend pages cannot validate the value proposition

### 2. Runtime and test baseline are broken

The backend creates database tables during module import. This makes app startup and tests depend on a live database connection.

Relevant files:

- [backend/app/main.py](/Users/chenbin/router/backend/app/main.py:8)
- [backend/app/db.py](/Users/chenbin/router/backend/app/db.py:6)
- [backend/tests/test_health.py](/Users/chenbin/router/backend/tests/test_health.py:7)

Observed issues:

- `pytest -q` fails during test collection because importing the app attempts a DB connection
- Health test expects `{"ok": True}` while the endpoint returns `{"status": "healthy"}`

Impact:

- No dependable local development loop
- No CI safety net
- Even basic refactors will be risky

### 3. Frontend and backend are not wired together correctly

The frontend points to a backend base URL that does not match the running backend.

Relevant files:

- [frontend/src/api/client.ts](/Users/chenbin/router/frontend/src/api/client.ts:12)
- [start.sh](/Users/chenbin/router/start.sh:18)

Observed issues:

- Frontend uses `http://localhost:<port>/api`
- Backend exposes routes without `/api`
- `start.sh` launches backend on port `8159`, while frontend defaults to `8080`

Impact:

- UI requests will fail even if the backend is running
- Demo reliability is low

### 4. Admin console is mostly static and not functional

A large part of the frontend is presentational. Many API functions are empty stubs and several pages depend on types or responses that do not actually exist.

Relevant files:

- [frontend/src/api/index.ts](/Users/chenbin/router/frontend/src/api/index.ts:4)
- [frontend/src/pages/DashboardAdminPage.tsx](/Users/chenbin/router/frontend/src/pages/DashboardAdminPage.tsx:18)
- [frontend/src/pages/ByokAdminPage.tsx](/Users/chenbin/router/frontend/src/pages/ByokAdminPage.tsx:7)
- [frontend/src/pages/LogsAdminPage.tsx](/Users/chenbin/router/frontend/src/pages/LogsAdminPage.tsx:7)

Observed issues:

- BYOK, credits, logs, organizations, providers, notifications APIs are placeholders
- Multiple pages expect data from functions that return `void`
- The app builds with Vite, but strict type-checking fails

Impact:

- The UI suggests capabilities that the system does not have
- Product review can overestimate maturity

### 5. Domain model is far behind the PRD

The current schema is too thin for a real AI gateway and also contains implementation issues.

Relevant files:

- [backend/app/models.py](/Users/chenbin/router/backend/app/models.py:5)
- [database/init.sql](/Users/chenbin/router/database/init.sql:1)

Observed gaps:

- No provider credentials model
- No route policy model
- No API key model
- No environment model
- No budget or quota model
- No audit log model
- No token usage or normalized cost detail fields
- `Project.organization` uses `back_populates="projects"` but `Organization.projects` is missing

Impact:

- Core features from the PRD cannot be implemented cleanly
- Migration path will become more expensive if postponed

### 6. Security and governance are not started

The current app is open by default and lacks enterprise guardrails.

Relevant files:

- [backend/app/main.py](/Users/chenbin/router/backend/app/main.py:12)

Observed gaps:

- Wildcard CORS
- No authentication
- No authorization or RBAC
- No encrypted secret storage
- No audit trail
- No rate limiting

Impact:

- Not suitable for enterprise trials
- Cannot support BYOK safely

## Comparison to Mainstream OpenSwitch Products

Compared with leading model gateways in the market, this project is currently missing the baseline capabilities customers expect.

### OpenRouter-style baseline

Expected:

- OpenAI-compatible unified API
- Real model fallback
- Real model routing
- BYOK support
- Reliable model catalog

Current gap:

- Only route names exist at the API level
- No provider execution path exists yet

Reference:

- [OpenRouter model routing](https://openrouter.ai/docs/model-routing)
- [OpenRouter BYOK](https://openrouter.ai/docs/docs/overview/auth/byok)

### Portkey-style baseline

Expected:

- Advanced routing
- Retries and circuit breaking
- Load balancing
- Guardrails
- Observability
- Budget controls

Current gap:

- None of these behaviors are implemented in the gateway layer

Reference:

- [Portkey AI Gateway](https://portkey.ai/docs/portkey-features/ai-gateway)

### LiteLLM-style baseline

Expected:

- Multi-provider translation layer
- Proxy-based auth and virtual keys
- Spend tracking
- Multi-tenant controls
- Usable admin workflow

Current gap:

- No provider abstraction layer
- No secure key model
- No real spend tracking

Reference:

- [LiteLLM docs](https://docs.litellm.ai/)

## Key Deficiencies by Priority

### P0: Must fix before positioning this as a working product

- Replace placeholder backend logic with real provider-backed execution
- Fix startup, DB initialization, and test isolation
- Align frontend and backend base paths and ports
- Implement real API contracts for currently visible admin features

### P1: Must fix before customer pilot

- Add authentication, API keys, tenant isolation, and request logging
- Introduce provider registry, route rules, and health status tracking
- Add fallback, timeout, retry, and error normalization
- Add normalized token and cost accounting

### P2: Needed for enterprise credibility

- BYOK encrypted storage and rotation
- RBAC and audit logs
- Budget and quota controls
- Alerting and admin notifications
- Dashboard metrics and export reliability

## Recommended Product Strategy

Do not optimize for feature breadth yet.

Recommended repositioning for the next phase:

- Goal: build a working AI gateway MVP
- Target user: platform or infra teams needing multi-model switching
- Core promise: switch providers without app code changes, with measurable reliability improvement

For the next MVP, prioritize only:

- Unified OpenAI-compatible API
- Provider abstraction for at least 2 upstreams
- Static routing plus fallback
- Request logs
- Token and cost normalization
- Basic API key auth

Delay until later:

- Rich admin console
- Advanced billing
- Full BYOK workflows
- Complex governance panels
- "Smart routing"

## 8-Week Optimization Plan

### Week 1: Stabilize the foundation

Goals:

- Make local development, startup, and tests reliable

Tasks:

- Remove import-time `create_all()` side effects
- Move DB initialization to explicit startup or migration flow
- Standardize config loading through one settings module
- Default local/test DB to SQLite
- Fix health endpoint contract and test expectation mismatch
- Add a minimal backend README with run and test commands
- Add frontend type-check script and backend test script

Exit criteria:

- `pytest -q` passes locally
- `tsc --noEmit` passes locally
- App starts from a documented command without manual patching

### Week 2: Fix the integration surface

Goals:

- Make the current frontend and backend communicate correctly

Tasks:

- Align frontend `baseURL` with backend host, port, and path
- Add versioned API prefix if desired, but make both sides consistent
- Replace placeholder frontend API methods with real implementations or hide those pages
- Remove or disable non-functional navigation items

Exit criteria:

- Core pages can load real backend responses
- Demo flow does not fail due to path or port mismatch

### Week 3: Build provider abstraction

Goals:

- Support real upstream model calls

Tasks:

- Introduce provider adapter interface
- Add at least 2 upstream providers
- Normalize request and response formats
- Normalize error handling across providers

Exit criteria:

- One request can be sent to at least 2 different providers through the same API

### Week 4: Implement routing and fallback

Goals:

- Deliver the product's main promise

Tasks:

- Add provider and route tables
- Implement preferred and backup provider logic
- Add timeout handling
- Add basic retry rules
- Record `fallback_used`, chosen provider, latency, and status

Exit criteria:

- Forced primary-provider failure falls back successfully to backup
- Request logs show the final routed provider

### Week 5: Add auth, usage, and billing basics

Goals:

- Make the gateway usable by real tenants

Tasks:

- Add API key model and auth middleware
- Add organization and project scoping
- Record prompt tokens, completion tokens, total cost
- Add billing usage query and CSV export

Exit criteria:

- Authenticated tenants can call the API and see isolated usage records

### Week 6: Tighten admin workflows

Goals:

- Turn the admin UI into a working console

Tasks:

- Implement model management APIs
- Implement provider management APIs
- Implement route management APIs
- Implement logs and dashboard read APIs
- Remove hard-coded table data

Exit criteria:

- Console actions persist data and reflect actual system state

### Week 7: Add BYOK and budget controls

Goals:

- Support a real commercial deployment pattern

Tasks:

- Add encrypted BYOK storage
- Add BYOK scoping by organization or project
- Add quotas or budget limits
- Add rejection paths for exhausted budgets

Exit criteria:

- BYOK request path works end to end
- Budget-limited tenant is blocked predictably

### Week 8: Production readiness pass

Goals:

- Prepare for pilot use

Tasks:

- Add structured logs and metrics
- Add audit events for admin actions
- Restrict CORS and tighten security defaults
- Add smoke tests for routing, fallback, auth, and billing
- Add deployment documentation

Exit criteria:

- MVP can be demoed or piloted with controlled users

## Suggested Backlog Structure

### Epic 1: Platform Foundation

- Config unification
- App startup cleanup
- DB migration setup
- Test reliability
- CI baseline

### Epic 2: Gateway Core

- Provider adapter abstraction
- OpenAI-compatible request mapping
- OpenAI-compatible response mapping
- Error normalization

### Epic 3: Routing Engine

- Provider registry
- Route policy model
- Timeout and retry policy
- Fallback execution
- Health status tracking

### Epic 4: Tenant and Billing

- API key auth
- Organization and project scoping
- Usage metering
- Cost normalization
- Billing export

### Epic 5: Control Plane

- Model admin APIs
- Provider admin APIs
- Route admin APIs
- Logs API
- Dashboard API

### Epic 6: Governance

- BYOK secret management
- RBAC
- Audit logs
- Budget controls
- Alerting

## Final Recommendation

This project is worth continuing, but it should not be treated as feature-complete.

The right move now is not adding more pages. The right move is narrowing the scope to a working gateway MVP and building the core execution path end to end.

If the next milestone is investor, partner, or customer-facing, the most important message should be:

"We have a functioning multi-model gateway with real provider switching and fallback."

Not:

"We have a broad admin console covering many future modules."
