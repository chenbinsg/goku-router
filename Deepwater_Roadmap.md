# Deepwater Roadmap

## Goal

Build `router` into an `AI traffic control plane for production workloads`, not just an OpenRouter-compatible gateway.

This roadmap assumes the competitive baseline is OpenRouter's currently documented platform surface as of `2026-04-29`, including:

- provider routing
- `openrouter/auto`
- structured outputs
- response healing
- prompt caching
- zero data retention controls
- workspaces
- guardrails
- usage accounting

Reference docs:

- [OpenRouter Provider Routing](https://openrouter.ai/docs/features/provider-routing)
- [OpenRouter Model Routing](https://openrouter.ai/docs/model-routing)
- [OpenRouter Structured Outputs](https://openrouter.ai/docs/features/structured-outputs)
- [OpenRouter Response Healing](https://openrouter.ai/docs/guides/features/plugins/response-healing)
- [OpenRouter Prompt Caching](https://openrouter.ai/docs/features/prompt-caching)
- [OpenRouter Zero Data Retention](https://openrouter.ai/docs/features/zdr)
- [OpenRouter Workspaces](https://openrouter.ai/docs/guides/features/workspaces/)
- [OpenRouter Guardrails](https://openrouter.ai/docs/guides/features/guardrails)
- [OpenRouter Usage Accounting](https://openrouter.ai/docs/guides/guides/administration/usage-accounting)

## Product Thesis

We win if customers believe:

1. `router` is easier to govern than OpenRouter.
2. `router` is more explainable than OpenRouter.
3. `router` is measurably better at routing for customer-specific workloads.
4. `router` can be deployed in stricter enterprise environments than OpenRouter.

## North Star

Primary north-star metric:

- `production traffic under managed routing`

Supporting metrics:

- `cost saved vs customer baseline`
- `successful responses rate`
- `schema success rate`
- `tool-call success rate`
- `policy-compliant requests rate`
- `mean incident detection time`
- `mean route-debug time`

## Phase 1: OpenRouter Parity+

Target:

- make migration easy
- remove obvious capability gaps
- make platform behavior explainable

Duration:

- `4-6 weeks`

Deliverables:

1. Full OpenAI-compatible request normalization
2. Strict tool calling support
3. Parallel tool calls support
4. Better structured outputs with repair pipeline
5. Prompt caching and sticky routing
6. Workspace-scoped routing defaults
7. API key lifecycle:
   - expiry
   - rotation
   - budget windows
   - scoped permissions
8. Route decision trace for every request

Acceptance criteria:

- a customer can switch from OpenRouter-compatible clients with minimal code change
- every request can be explained via trace:
  - requested model
  - candidate providers
  - rejected providers
  - selected provider
  - fallback path
  - policy decisions
  - cost and usage

## Phase 2: Eval-Driven Routing

Target:

- move from configurable routing to optimized routing

Duration:

- `6-8 weeks`

Deliverables:

1. Capability registry
2. Offline eval dataset framework
3. Multi-objective route scorer:
   - quality
   - cost
   - latency
   - reliability
4. Task classifier for route selection
5. `router/auto` v2 backed by evals, not only heuristics
6. Provider and model scorecards
7. Per-customer route policies and learned preferences

Acceptance criteria:

- for at least `3` real workload classes, router outperforms static routing
- route changes can be justified by benchmark evidence
- customers can compare:
  - cheapest route
  - safest route
  - fastest route
  - best quality route

## Phase 3: Enterprise Control Plane

Target:

- become adoptable for security-conscious and multi-team deployments

Duration:

- `6-10 weeks`

Deliverables:

1. Full tenancy hierarchy:
   - organization
   - workspace
   - project
   - environment
   - API key
   - agent/application
2. Policy engine
3. Region and data-residency controls
4. ZDR-aware routing
5. BYOK inheritance and overrides
6. Audit and approval workflows
7. Observability sinks and export integrations
8. Admin management API

Acceptance criteria:

- one enterprise account can safely isolate production, staging, and internal research
- auditors can reconstruct access and policy decisions
- security teams can restrict models, providers, tools, and data policy by scope

## Phase 4: Beyond OpenRouter

Target:

- create reasons to choose `router` even when OpenRouter is already acceptable

Duration:

- `8-12 weeks`

Deliverables:

1. Route simulator
2. Route A/B testing
3. Workflow-level cost optimizer
4. Agent-aware routing
5. Streaming repair and continuation
6. Runtime policy recommendations
7. Single-tenant and private-region deployment options
8. SLA and savings reporting

Acceptance criteria:

- customer can simulate savings before migration
- customer can run controlled experiments on routing strategy
- customer can prove compliance and savings to procurement or platform leadership

## Workstreams

### Workstream A: Protocol Layer

Owner:

- backend platform

Scope:

- request normalization
- provider adapters
- streaming semantics
- structured output repair
- tool-calling transforms

### Workstream B: Routing Intelligence

Owner:

- ML systems / infra

Scope:

- capability graph
- scoring models
- eval pipelines
- learned routing policies

### Workstream C: Governance

Owner:

- platform backend

Scope:

- workspaces
- policies
- budgets
- audit
- approvals
- ZDR / residency constraints

### Workstream D: Observability

Owner:

- data / infra

Scope:

- traces
- analytics
- replay
- alerts
- anomaly detection

### Workstream E: Product Surface

Owner:

- frontend / product engineering

Scope:

- control plane UI
- simulator
- analytics
- customer debugging tools

## Dependencies

Phase 2 depends on:

- clean trace data
- stable cost accounting
- capability registry

Phase 3 depends on:

- consistent tenancy model
- policy enforcement hooks in request pipeline

Phase 4 depends on:

- historical traffic data
- trustworthy eval harness
- user-visible analytics

## Risks

1. Overfitting routing to synthetic tests
2. Building too many controls before routing quality is truly better
3. Enterprise complexity slowing down basic DX
4. Provider behavior drift invalidating capability assumptions
5. Weak observability making "smart routing" impossible to trust

## Recommendation

Execute in this order:

1. protocol parity and explainability
2. eval-driven routing
3. enterprise governance
4. simulator and optimization moat

Do not market "better than OpenRouter" until Phase 2 metrics are real.
