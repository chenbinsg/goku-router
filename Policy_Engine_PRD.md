# Policy Engine PRD

## Objective

Design a programmable policy engine that makes `router` safer, more governable, and more enterprise-ready than OpenRouter-style guardrails.

The engine should support:

- route eligibility decisions
- budget enforcement
- data policy enforcement
- model and provider restrictions
- tool access control
- environment scoping
- explainable rejection reasons

## Problem

Simple allowlists are not enough for production AI traffic.

Customers need policies such as:

- staging can use cheap models, production cannot
- finance workloads must use ZDR-compatible providers only
- one team may use tool calling, another may not
- some API keys can use vision, others cannot
- some projects may exceed latency budgets, others may not
- nightly batch jobs may use slower cheaper routes

## Users

1. Platform admin
2. Security admin
3. AI platform engineer
4. Team lead
5. Compliance / audit owner

## Policy Scopes

Policies can be attached at:

1. account
2. organization
3. workspace
4. project
5. environment
6. API key
7. application / agent

Lower scopes may only be more restrictive unless explicitly configured otherwise.

## Policy Types

### Budget policy

Fields:

- limit amount
- reset interval
- whether BYOK counts
- hard block or soft alert

### Model policy

Fields:

- allowed models
- denied models
- reasoning model allowlist
- max context window

### Provider policy

Fields:

- allowed providers
- denied providers
- preferred provider groups
- region restrictions

### Data policy

Fields:

- require ZDR
- allowed retention modes
- data export allowed
- trace retention days

### Capability policy

Fields:

- allow tool calling
- allow parallel tool calls
- allow structured outputs
- allow multimodal input
- allow web/plugin usage

### Output policy

Fields:

- required response format
- schema strictness
- repair allowed
- max output tokens

### Safety policy

Fields:

- blocked words
- blocked regex patterns
- sensitive tool denylist
- moderation routing required

## Policy Evaluation Model

Request evaluation happens in this order:

1. identify request scope
2. merge inherited policies
3. compute effective constraints
4. reject ineligible models/providers
5. score remaining candidates
6. emit decision trace

## Merge Rules

Use deterministic merge rules:

- deny beats allow
- lower budget wins
- stricter retention wins
- narrower capability set wins
- explicit key-level restriction beats workspace default

## Decision Output

Every policy evaluation should produce:

- `allowed: true/false`
- `rejection_reason`
- `effective_scope_chain`
- `effective_budget`
- `effective_allowed_models`
- `effective_allowed_providers`
- `effective_data_policy`
- `effective_capability_policy`

## Explainability Requirement

The policy engine is incomplete unless admins can answer:

- why was this request blocked?
- which scope created the block?
- which policy field applied?
- what would make the request pass?

## Admin UX Requirements

1. Policy list view
2. Scope assignment UI
3. Eligibility preview
4. "Why blocked?" inspector
5. Diff view for policy changes
6. Dry-run mode before enforcement

## API Requirements

Must support:

- create policy
- update policy
- delete policy
- assign policy to scope
- preview policy eligibility
- fetch effective policy for request context
- export audit records

## Analytics Requirements

Need metrics for:

- policy block rate
- top rejection reasons
- spend prevented by policies
- blocked provider/model attempts
- dry-run vs live decision differences

## Rollout Plan

### Stage 1

- model allow/deny
- provider allow/deny
- blocked words
- max prompt length

### Stage 2

- budgets
- ZDR
- tool calling restrictions
- environment scopes

### Stage 3

- dry-run mode
- eligibility preview
- policy diff and versioning

### Stage 4

- delegated approvals
- scheduled policy windows
- anomaly-triggered policy escalation

## Non-Goals

This engine should not initially:

- replace all moderation systems
- make legal/compliance judgments automatically
- auto-write policies without human review

## Success Criteria

1. Admin can restrict traffic by team, environment, and key.
2. Every blocked request has a deterministic reason.
3. Customers can adopt stricter compliance postures than generic gateway defaults.
4. Policy support becomes a sales differentiator, not just an internal control feature.
