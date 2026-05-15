# Eval Report: sales_ops_agent_pack

## Strategies

- `static_primary_backup`
- `cheapest_provider`
- `fastest_provider`
- `openrouter_like_auto`
- `current_production_policy`

## Summary

| Strategy | Requests | Success Rate | Schema Rate | Tool Rate | Avg Latency (ms) | Avg Cost | Avg Score | Score vs Baseline | Cost vs Baseline |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `cheapest_provider` | 4 | 100.00% | 100.00% | 100.00% | 0.035 | 0.0204 | 0.8662 | 0.0 | -0.0097 |
| `current_production_policy` | 4 | 100.00% | 100.00% | 100.00% | 0.025 | 0.0301 | 0.8662 | 0.0 | 0.0 |
| `fastest_provider` | 4 | 100.00% | 100.00% | 100.00% | 0.026 | 0.0301 | 0.8662 | 0.0 | 0.0 |
| `openrouter_like_auto` | 4 | 100.00% | 100.00% | 100.00% | 0.026 | 0.0204 | 0.8662 | 0.0 | -0.0097 |
| `static_primary_backup` | 4 | 100.00% | 100.00% | 100.00% | 0.036 | 0.0301 | 0.8662 | 0.0 | 0.0 |

## Workload Winners

| Workload | Winner Strategy | Winner Score | Winner Cost | Winner Latency (ms) |
| --- | --- | ---: | ---: | ---: |
| `long_context` | `openrouter_like_auto` | 0.85 | 0.0366 | 0.019 |
| `multimodal_vision` | `openrouter_like_auto` | 0.9016 | 0.0164 | 0.014 |
| `structured_extraction` | `openrouter_like_auto` | 0.85 | 0.0122 | 0.047 |
| `tool_use` | `openrouter_like_auto` | 0.8633 | 0.0164 | 0.022 |

## Workload Breakdown

| Workload | Strategy | Requests | Avg Score | Avg Cost | Avg Latency (ms) | Schema Rate | Tool Rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `long_context` | `cheapest_provider` | 1 | 0.85 | 0.0366 | 0.022 | 100.00% | 100.00% |
| `long_context` | `current_production_policy` | 1 | 0.85 | 0.067 | 0.019 | 100.00% | 100.00% |
| `long_context` | `fastest_provider` | 1 | 0.85 | 0.067 | 0.022 | 100.00% | 100.00% |
| `long_context` | `openrouter_like_auto` | 1 | 0.85 | 0.0366 | 0.019 | 100.00% | 100.00% |
| `long_context` | `static_primary_backup` | 1 | 0.85 | 0.067 | 0.031 | 100.00% | 100.00% |
| `multimodal_vision` | `cheapest_provider` | 1 | 0.9016 | 0.0164 | 0.035 | 100.00% | 100.00% |
| `multimodal_vision` | `current_production_policy` | 1 | 0.9016 | 0.0164 | 0.016 | 100.00% | 100.00% |
| `multimodal_vision` | `fastest_provider` | 1 | 0.9016 | 0.0164 | 0.016 | 100.00% | 100.00% |
| `multimodal_vision` | `openrouter_like_auto` | 1 | 0.9016 | 0.0164 | 0.014 | 100.00% | 100.00% |
| `multimodal_vision` | `static_primary_backup` | 1 | 0.9016 | 0.0164 | 0.018 | 100.00% | 100.00% |
| `structured_extraction` | `cheapest_provider` | 1 | 0.85 | 0.0122 | 0.056 | 100.00% | 100.00% |
| `structured_extraction` | `current_production_policy` | 1 | 0.85 | 0.0206 | 0.041 | 100.00% | 100.00% |
| `structured_extraction` | `fastest_provider` | 1 | 0.85 | 0.0206 | 0.041 | 100.00% | 100.00% |
| `structured_extraction` | `openrouter_like_auto` | 1 | 0.85 | 0.0122 | 0.047 | 100.00% | 100.00% |
| `structured_extraction` | `static_primary_backup` | 1 | 0.85 | 0.0206 | 0.061 | 100.00% | 100.00% |
| `tool_use` | `cheapest_provider` | 1 | 0.8633 | 0.0164 | 0.026 | 100.00% | 100.00% |
| `tool_use` | `current_production_policy` | 1 | 0.8633 | 0.0164 | 0.023 | 100.00% | 100.00% |
| `tool_use` | `fastest_provider` | 1 | 0.8633 | 0.0164 | 0.024 | 100.00% | 100.00% |
| `tool_use` | `openrouter_like_auto` | 1 | 0.8633 | 0.0164 | 0.022 | 100.00% | 100.00% |
| `tool_use` | `static_primary_backup` | 1 | 0.8633 | 0.0164 | 0.032 | 100.00% | 100.00% |

## Decision Highlights

### `long_context` / `static_primary_backup`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output

### `long_context` / `cheapest_provider`
- Selected provider: `provider_backup`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output

### `long_context` / `fastest_provider`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output

### `long_context` / `openrouter_like_auto`
- Selected provider: `provider_backup`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output

### `long_context` / `current_production_policy`
- Selected provider: `provider_backup`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output

### `tool_use` / `static_primary_backup`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

### `tool_use` / `cheapest_provider`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

### `tool_use` / `fastest_provider`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

### `tool_use` / `openrouter_like_auto`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

### `tool_use` / `current_production_policy`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

### `structured_extraction` / `static_primary_backup`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output

### `structured_extraction` / `cheapest_provider`
- Selected provider: `provider_backup`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output

### `structured_extraction` / `fastest_provider`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output

### `structured_extraction` / `openrouter_like_auto`
- Selected provider: `provider_backup`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output

### `structured_extraction` / `current_production_policy`
- Selected provider: `provider_backup`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output

### `multimodal_vision` / `static_primary_backup`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

### `multimodal_vision` / `cheapest_provider`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

### `multimodal_vision` / `fastest_provider`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

### `multimodal_vision` / `openrouter_like_auto`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

### `multimodal_vision` / `current_production_policy`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`
- Rejected candidate: `provider_backup` reason=`missing_required_capabilities`

