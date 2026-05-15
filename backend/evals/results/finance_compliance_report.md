# Eval Report: finance_compliance_pack

## Strategies

- `static_primary_backup`
- `cheapest_provider`
- `fastest_provider`
- `openrouter_like_auto`
- `current_production_policy`

## Summary

| Strategy | Requests | Success Rate | Failure Rate | Schema Rate | Tool Rate | Avg Latency (ms) | Avg Cost | Avg Score | Score vs Baseline | Cost vs Baseline |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `cheapest_provider` | 4 | 100.00% | 0.00% | 100.00% | 100.00% | 0.049 | 0.01455 | 0.8827 | 0.0 | 0.0 |
| `current_production_policy` | 4 | 100.00% | 0.00% | 100.00% | 100.00% | 0.031 | 0.01455 | 0.8827 | 0.0 | 0.0 |
| `fastest_provider` | 4 | 100.00% | 0.00% | 100.00% | 100.00% | 0.033 | 0.01455 | 0.8827 | 0.0 | 0.0 |
| `openrouter_like_auto` | 4 | 100.00% | 0.00% | 100.00% | 100.00% | 0.043 | 0.01455 | 0.8827 | 0.0 | 0.0 |
| `static_primary_backup` | 4 | 100.00% | 0.00% | 100.00% | 100.00% | 0.039 | 0.01455 | 0.8827 | 0.0 | 0.0 |

## Workload Winners

| Workload | Winner Strategy | Winner Score | Winner Cost | Winner Latency (ms) |
| --- | --- | ---: | ---: | ---: |
| `classification` | `current_production_policy` | 0.874 | 0.0084 | 0.017 |
| `multimodal_vision` | `cheapest_provider` | 0.9214 | 0.0131 | 0.016 |
| `structured_extraction` | `current_production_policy` | 0.85 | 0.0214 | 0.063 |
| `tool_use` | `current_production_policy` | 0.8852 | 0.0153 | 0.026 |

## Workload Breakdown

| Workload | Strategy | Requests | Avg Score | Avg Cost | Avg Latency (ms) | Failure Rate | Schema Rate | Tool Rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `classification` | `cheapest_provider` | 1 | 0.874 | 0.0084 | 0.049 | 0.00% | 100.00% | 100.00% |
| `classification` | `current_production_policy` | 1 | 0.874 | 0.0084 | 0.017 | 0.00% | 100.00% | 100.00% |
| `classification` | `fastest_provider` | 1 | 0.874 | 0.0084 | 0.017 | 0.00% | 100.00% | 100.00% |
| `classification` | `openrouter_like_auto` | 1 | 0.874 | 0.0084 | 0.026 | 0.00% | 100.00% | 100.00% |
| `classification` | `static_primary_backup` | 1 | 0.874 | 0.0084 | 0.022 | 0.00% | 100.00% | 100.00% |
| `multimodal_vision` | `cheapest_provider` | 1 | 0.9214 | 0.0131 | 0.016 | 0.00% | 100.00% | 100.00% |
| `multimodal_vision` | `current_production_policy` | 1 | 0.9214 | 0.0131 | 0.02 | 0.00% | 100.00% | 100.00% |
| `multimodal_vision` | `fastest_provider` | 1 | 0.9214 | 0.0131 | 0.018 | 0.00% | 100.00% | 100.00% |
| `multimodal_vision` | `openrouter_like_auto` | 1 | 0.9214 | 0.0131 | 0.018 | 0.00% | 100.00% | 100.00% |
| `multimodal_vision` | `static_primary_backup` | 1 | 0.9214 | 0.0131 | 0.02 | 0.00% | 100.00% | 100.00% |
| `structured_extraction` | `cheapest_provider` | 1 | 0.85 | 0.0214 | 0.097 | 0.00% | 100.00% | 100.00% |
| `structured_extraction` | `current_production_policy` | 1 | 0.85 | 0.0214 | 0.063 | 0.00% | 100.00% | 100.00% |
| `structured_extraction` | `fastest_provider` | 1 | 0.85 | 0.0214 | 0.063 | 0.00% | 100.00% | 100.00% |
| `structured_extraction` | `openrouter_like_auto` | 1 | 0.85 | 0.0214 | 0.1 | 0.00% | 100.00% | 100.00% |
| `structured_extraction` | `static_primary_backup` | 1 | 0.85 | 0.0214 | 0.082 | 0.00% | 100.00% | 100.00% |
| `tool_use` | `cheapest_provider` | 1 | 0.8852 | 0.0153 | 0.036 | 0.00% | 100.00% | 100.00% |
| `tool_use` | `current_production_policy` | 1 | 0.8852 | 0.0153 | 0.026 | 0.00% | 100.00% | 100.00% |
| `tool_use` | `fastest_provider` | 1 | 0.8852 | 0.0153 | 0.033 | 0.00% | 100.00% | 100.00% |
| `tool_use` | `openrouter_like_auto` | 1 | 0.8852 | 0.0153 | 0.028 | 0.00% | 100.00% | 100.00% |
| `tool_use` | `static_primary_backup` | 1 | 0.8852 | 0.0153 | 0.033 | 0.00% | 100.00% | 100.00% |

## Decision Highlights

### `structured_extraction` / `static_primary_backup`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling,zdr
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

### `structured_extraction` / `cheapest_provider`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling,zdr
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

### `structured_extraction` / `fastest_provider`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling,zdr
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

### `structured_extraction` / `openrouter_like_auto`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling,zdr
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

### `structured_extraction` / `current_production_policy`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling,zdr
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

### `classification` / `static_primary_backup`
- Selected provider: `provider_backup`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output
- Rejected candidate: `provider_primary` reason=`price_above_request_budget`

### `classification` / `cheapest_provider`
- Selected provider: `provider_backup`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output
- Rejected candidate: `provider_primary` reason=`price_above_request_budget`

### `classification` / `fastest_provider`
- Selected provider: `provider_backup`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output
- Rejected candidate: `provider_primary` reason=`price_above_request_budget`

### `classification` / `openrouter_like_auto`
- Selected provider: `provider_backup`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output
- Rejected candidate: `provider_primary` reason=`price_above_request_budget`

### `classification` / `current_production_policy`
- Selected provider: `provider_backup`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output
- Rejected candidate: `provider_primary` reason=`price_above_request_budget`

### `tool_use` / `static_primary_backup`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling,zdr
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

### `tool_use` / `cheapest_provider`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling,zdr
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

### `tool_use` / `fastest_provider`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling,zdr
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

### `tool_use` / `openrouter_like_auto`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling,zdr
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

### `tool_use` / `current_production_policy`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling,zdr
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

### `multimodal_vision` / `static_primary_backup`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling,zdr
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

### `multimodal_vision` / `cheapest_provider`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling,zdr
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

### `multimodal_vision` / `fastest_provider`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling,zdr
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

### `multimodal_vision` / `openrouter_like_auto`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling,zdr
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

### `multimodal_vision` / `current_production_policy`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling,zdr
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`


## Shadow Comparisons

| Example | Workload | Strategy | Score Delta | Cost Delta | Latency Delta (ms) | Winner |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `finance-multimodal-1` | `multimodal_vision` | `cheapest_provider` | 0.0 | 0.0 | -0.004 | `cheapest_provider` |
| `finance-multimodal-1` | `multimodal_vision` | `fastest_provider` | 0.0 | 0.0 | -0.002 | `fastest_provider` |
| `finance-multimodal-1` | `multimodal_vision` | `openrouter_like_auto` | 0.0 | 0.0 | -0.002 | `openrouter_like_auto` |
| `finance-multimodal-1` | `multimodal_vision` | `static_primary_backup` | -0.0 | 0.0 | 0.001 | `current_production_policy` |
| `finance-policy-1` | `classification` | `cheapest_provider` | -0.0 | 0.0 | 0.032 | `current_production_policy` |
| `finance-policy-1` | `classification` | `fastest_provider` | 0.0 | 0.0 | -0.0 | `fastest_provider` |
| `finance-policy-1` | `classification` | `openrouter_like_auto` | -0.0 | 0.0 | 0.01 | `current_production_policy` |
| `finance-policy-1` | `classification` | `static_primary_backup` | -0.0 | 0.0 | 0.005 | `current_production_policy` |
| `finance-tool-1` | `tool_use` | `cheapest_provider` | -0.0 | 0.0 | 0.009 | `current_production_policy` |
| `finance-tool-1` | `tool_use` | `fastest_provider` | -0.0 | 0.0 | 0.006 | `current_production_policy` |
| `finance-tool-1` | `tool_use` | `openrouter_like_auto` | -0.0 | 0.0 | 0.002 | `current_production_policy` |
| `finance-tool-1` | `tool_use` | `static_primary_backup` | -0.0 | 0.0 | 0.007 | `current_production_policy` |
| `finance-zdr-1` | `structured_extraction` | `cheapest_provider` | -0.0 | 0.0 | 0.034 | `current_production_policy` |
| `finance-zdr-1` | `structured_extraction` | `fastest_provider` | -0.0 | 0.0 | 0.001 | `current_production_policy` |
| `finance-zdr-1` | `structured_extraction` | `openrouter_like_auto` | -0.0 | 0.0 | 0.038 | `current_production_policy` |
| `finance-zdr-1` | `structured_extraction` | `static_primary_backup` | -0.0 | 0.0 | 0.019 | `current_production_policy` |

## Policy Dry Run

| Case | Example | Strategy | Blocked | Block Reason | Selected Provider | Accepted Candidates | Rejected Candidates |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| `deny-primary-provider` | `finance-zdr-1` | `static_primary_backup` | `False` | `None` | `None` | 0 | 2 |
| `deny-primary-provider` | `finance-zdr-1` | `cheapest_provider` | `False` | `None` | `None` | 0 | 2 |
| `deny-primary-provider` | `finance-zdr-1` | `fastest_provider` | `False` | `None` | `None` | 0 | 2 |
| `deny-primary-provider` | `finance-zdr-1` | `openrouter_like_auto` | `False` | `None` | `None` | 0 | 3 |
| `deny-primary-provider` | `finance-zdr-1` | `current_production_policy` | `False` | `None` | `None` | 0 | 2 |
| `blocked-keyword-policy` | `finance-policy-1` | `static_primary_backup` | `True` | `guardrail_blocked_word` | `provider_backup` | 1 | 1 |
| `blocked-keyword-policy` | `finance-policy-1` | `cheapest_provider` | `True` | `guardrail_blocked_word` | `provider_backup` | 1 | 1 |
| `blocked-keyword-policy` | `finance-policy-1` | `fastest_provider` | `True` | `guardrail_blocked_word` | `provider_backup` | 1 | 1 |
| `blocked-keyword-policy` | `finance-policy-1` | `openrouter_like_auto` | `True` | `guardrail_blocked_word` | `provider_backup` | 2 | 1 |
| `blocked-keyword-policy` | `finance-policy-1` | `current_production_policy` | `True` | `guardrail_blocked_word` | `provider_backup` | 1 | 1 |
