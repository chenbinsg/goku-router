# Routing Eval Spec

## Purpose

Define how `router` proves that its routing is better than:

- fixed primary/backup routing
- manual provider selection
- OpenRouter-style generic auto routing

This document exists to prevent "smart routing" from becoming a marketing claim without evidence.

## Eval Questions

The routing system must answer:

1. Does it reduce cost for the same acceptable output quality?
2. Does it improve success rate under provider instability?
3. Does it improve schema success rate?
4. Does it improve tool-call success rate?
5. Does it reduce latency for latency-sensitive tasks?
6. Can it explain why a route was chosen?

## Evaluation Modes

### Offline replay

Use historical prompts and compare candidate route decisions without live customer impact.

Best for:

- route scoring iteration
- regression detection
- policy validation

### Shadow routing

Production request goes to primary path, but router computes and records alternative route decisions in parallel.

Best for:

- comparing decisions before rollout
- validating expected savings

### Online A/B routing

Split traffic between route policies.

Best for:

- proving business value
- validating customer-visible outcomes

## Workload Buckets

Every eval example must belong to one primary workload class:

1. `chat_general`
2. `chat_reasoning`
3. `structured_extraction`
4. `tool_use`
5. `classification`
6. `multimodal_vision`
7. `long_context`
8. `latency_sensitive`

## Eval Dataset Schema

Each example should include:

- `example_id`
- `tenant_id`
- `workload_class`
- `messages`
- `required_capabilities`
- `response_format`
- `tools`
- `latency_budget_ms`
- `max_cost_usd`
- `quality_rubric`
- `ground_truth` if available
- `safety_constraints`

## Candidate Route Inputs

Each route decision should evaluate:

- model
- provider
- provider endpoint
- expected cost
- expected latency
- provider health
- capability support
- policy compatibility
- historical quality score for this workload class

## Core Metrics

### Reliability

- `request_success_rate`
- `first_attempt_success_rate`
- `fallback_rate`
- `provider_error_rate`
- `policy_rejection_rate`

### Quality

- `human_preference_win_rate`
- `task_completion_rate`
- `schema_valid_rate`
- `tool_call_success_rate`
- `output_repair_rate`

### Speed

- `p50_latency_ms`
- `p95_latency_ms`
- `time_to_first_token_ms`
- `stream_interrupt_rate`

### Cost

- `cost_per_request`
- `cost_per_successful_request`
- `cost_per_valid_schema`
- `cache_hit_adjusted_cost`

### Explainability

- `decision_trace_coverage`
- `trace_replay_success_rate`
- `route_reason_completeness`

## Route Score Function

Initial route score:

`score = quality_weight * quality_score - cost_weight * normalized_cost - latency_weight * normalized_latency + reliability_weight * reliability_score`

Additional hard filters:

- missing required capability
- violates policy
- exceeds budget
- not ZDR-compatible when required
- not region-compatible

## Quality Scoring

### Human judged

For the highest-value workloads:

- pairwise compare outputs from two routes
- judge:
  - correctness
  - completeness
  - format validity
  - usefulness

### Programmatic

For scalable coverage:

- exact match
- rubric scoring
- schema validation
- tool execution success
- JSON parse success

## Baselines

Every new routing policy must be compared against:

1. `static_primary_backup`
2. `cheapest_provider`
3. `fastest_provider`
4. `best_historical_quality`
5. `current_production_policy`
6. `openrouter_like_auto`

## Acceptance Thresholds

A new route policy may ship only if:

- total success rate is not worse by more than `0.2%`
- schema valid rate is improved or unchanged
- tool-call success rate is improved or unchanged
- cost per successful request improves by at least `5%` in the targeted workload
- p95 latency does not regress beyond agreed budget

## Rollout Rules

1. Offline replay passes
2. Shadow routing shows expected improvement
3. Small A/B rollout
4. Expand by workload class, not all traffic at once

## Failure Analysis

For every losing route decision, classify the failure:

- wrong provider chosen
- wrong model chosen
- stale health signal
- bad cost estimate
- capability mismatch
- policy mismatch
- bad tool compatibility assumption
- bad schema compatibility assumption
- prompt compression damage

## Observability Requirements

Each eval result must store:

- request fingerprint
- chosen route
- alternative top 3 routes
- score components
- final outcome
- response usage
- failure category

## Artifacts

The eval system should output:

1. leaderboard by route policy
2. scorecards by workload class
3. regression report by release
4. customer-specific routing report

## Shipping Principle

Do not ship a routing strategy because it "looks smarter".

Ship it only when:

- it wins on measured customer workloads
- its failures are classifiable
- its decisions are explainable
