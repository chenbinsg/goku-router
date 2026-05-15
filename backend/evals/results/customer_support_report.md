# Eval Report: customer_support_pack

## Strategies

- `static_primary_backup`
- `cheapest_provider`
- `fastest_provider`
- `openrouter_like_auto`
- `current_production_policy`

## Summary

| Strategy | Requests | Success Rate | Schema Rate | Tool Rate | Avg Latency (ms) | Avg Cost | Avg Score | Score vs Baseline | Cost vs Baseline |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `cheapest_provider` | 4 | 100.00% | 100.00% | 100.00% | 0.035 | 0.0095 | 0.8742 | 0.0112 | -0.00565 |
| `current_production_policy` | 4 | 100.00% | 100.00% | 100.00% | 0.034 | 0.01515 | 0.863 | 0.0 | 0.0 |
| `fastest_provider` | 4 | 100.00% | 100.00% | 100.00% | 0.034 | 0.01515 | 0.863 | 0.0 | 0.0 |
| `openrouter_like_auto` | 4 | 100.00% | 100.00% | 100.00% | 0.031 | 0.0095 | 0.8742 | 0.0112 | -0.00565 |
| `static_primary_backup` | 4 | 100.00% | 100.00% | 100.00% | 0.037 | 0.01515 | 0.863 | 0.0 | 0.0 |

## Workload Winners

| Workload | Winner Strategy | Winner Score | Winner Cost | Winner Latency (ms) |
| --- | --- | ---: | ---: | ---: |
| `chat_general` | `openrouter_like_auto` | 0.85 | 0.0114 | 0.012 |
| `classification` | `openrouter_like_auto` | 0.85 | 0.0084 | 0.043 |
| `structured_extraction` | `openrouter_like_auto` | 0.895 | 0.0084 | 0.044 |
| `tool_use` | `fastest_provider` | 0.902 | 0.0098 | 0.024 |

## Workload Breakdown

| Workload | Strategy | Requests | Avg Score | Avg Cost | Avg Latency (ms) | Schema Rate | Tool Rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `chat_general` | `cheapest_provider` | 1 | 0.85 | 0.0114 | 0.013 | 100.00% | 100.00% |
| `chat_general` | `current_production_policy` | 1 | 0.85 | 0.0208 | 0.013 | 100.00% | 100.00% |
| `chat_general` | `fastest_provider` | 1 | 0.85 | 0.0208 | 0.014 | 100.00% | 100.00% |
| `chat_general` | `openrouter_like_auto` | 1 | 0.85 | 0.0114 | 0.012 | 100.00% | 100.00% |
| `chat_general` | `static_primary_backup` | 1 | 0.85 | 0.0208 | 0.012 | 100.00% | 100.00% |
| `classification` | `cheapest_provider` | 1 | 0.85 | 0.0084 | 0.052 | 100.00% | 100.00% |
| `classification` | `current_production_policy` | 1 | 0.85 | 0.0154 | 0.043 | 100.00% | 100.00% |
| `classification` | `fastest_provider` | 1 | 0.85 | 0.0154 | 0.046 | 100.00% | 100.00% |
| `classification` | `openrouter_like_auto` | 1 | 0.85 | 0.0084 | 0.043 | 100.00% | 100.00% |
| `classification` | `static_primary_backup` | 1 | 0.85 | 0.0154 | 0.06 | 100.00% | 100.00% |
| `structured_extraction` | `cheapest_provider` | 1 | 0.895 | 0.0084 | 0.051 | 100.00% | 100.00% |
| `structured_extraction` | `current_production_policy` | 1 | 0.85 | 0.0146 | 0.055 | 100.00% | 100.00% |
| `structured_extraction` | `fastest_provider` | 1 | 0.85 | 0.0146 | 0.051 | 100.00% | 100.00% |
| `structured_extraction` | `openrouter_like_auto` | 1 | 0.895 | 0.0084 | 0.044 | 100.00% | 100.00% |
| `structured_extraction` | `static_primary_backup` | 1 | 0.85 | 0.0146 | 0.051 | 100.00% | 100.00% |
| `tool_use` | `cheapest_provider` | 1 | 0.902 | 0.0098 | 0.026 | 100.00% | 100.00% |
| `tool_use` | `current_production_policy` | 1 | 0.902 | 0.0098 | 0.027 | 100.00% | 100.00% |
| `tool_use` | `fastest_provider` | 1 | 0.902 | 0.0098 | 0.024 | 100.00% | 100.00% |
| `tool_use` | `openrouter_like_auto` | 1 | 0.902 | 0.0098 | 0.025 | 100.00% | 100.00% |
| `tool_use` | `static_primary_backup` | 1 | 0.902 | 0.0098 | 0.025 | 100.00% | 100.00% |

## Decision Highlights

### `classification` / `static_primary_backup`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output

### `classification` / `cheapest_provider`
- Selected provider: `provider_backup`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output

### `classification` / `fastest_provider`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output

### `classification` / `openrouter_like_auto`
- Selected provider: `provider_backup`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output

### `classification` / `current_production_policy`
- Selected provider: `provider_backup`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output

### `chat_general` / `static_primary_backup`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output

### `chat_general` / `cheapest_provider`
- Selected provider: `provider_backup`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output

### `chat_general` / `fastest_provider`
- Selected provider: `provider_primary`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output

### `chat_general` / `openrouter_like_auto`
- Selected provider: `provider_backup`
- Selected model: `model1`
- Compression applied: `False`
- Accepted candidate: `provider_primary` price=1.1 latency=280.0 capabilities=chat,multimodal,structured_output,tool_calling
- Accepted candidate: `provider_backup` price=0.6 latency=360.0 capabilities=chat,structured_output

### `chat_general` / `current_production_policy`
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

