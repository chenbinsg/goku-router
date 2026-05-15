# Eval Report: sample_router_eval

## Strategies

- `static_primary_backup`
- `cheapest_provider`
- `fastest_provider`
- `openrouter_like_auto`
- `current_production_policy`

## Summary

| Strategy | Requests | Success Rate | Schema Rate | Tool Rate | Avg Latency (ms) | Avg Cost | Avg Score | Score vs Baseline | Cost vs Baseline |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `cheapest_provider` | 3 | 100.00% | 100.00% | 100.00% | 0.08 | 0.007367 | 0.9282 | 0.0307 | -0.003633 |
| `current_production_policy` | 3 | 100.00% | 100.00% | 100.00% | 0.08 | 0.011 | 0.8975 | 0.0 | 0.0 |
| `fastest_provider` | 3 | 100.00% | 100.00% | 100.00% | 0.062 | 0.011 | 0.8975 | 0.0 | 0.0 |
| `openrouter_like_auto` | 3 | 100.00% | 100.00% | 100.00% | 0.258 | 0.007367 | 0.9282 | 0.0307 | -0.003633 |
| `static_primary_backup` | 3 | 100.00% | 100.00% | 100.00% | 0.241 | 0.011 | 0.8975 | 0.0 | 0.0 |

## Workload Winners

| Workload | Winner Strategy | Winner Score | Winner Cost | Winner Latency (ms) |
| --- | --- | ---: | ---: | ---: |
| `chat_general` | `openrouter_like_auto` | 0.901 | 0.0066 | 0.035 |
| `structured_extraction` | `cheapest_provider` | 0.949 | 0.0068 | 0.112 |
| `tool_use` | `fastest_provider` | 0.9347 | 0.0087 | 0.055 |

## Workload Breakdown

| Workload | Strategy | Requests | Avg Score | Avg Cost | Avg Latency (ms) | Schema Rate | Tool Rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `chat_general` | `cheapest_provider` | 1 | 0.901 | 0.0066 | 0.039 | 100.00% | 100.00% |
| `chat_general` | `current_production_policy` | 1 | 0.85 | 0.012 | 0.034 | 100.00% | 100.00% |
| `chat_general` | `fastest_provider` | 1 | 0.85 | 0.012 | 0.036 | 100.00% | 100.00% |
| `chat_general` | `openrouter_like_auto` | 1 | 0.901 | 0.0066 | 0.035 | 100.00% | 100.00% |
| `chat_general` | `static_primary_backup` | 1 | 0.85 | 0.012 | 0.06 | 100.00% | 100.00% |
| `structured_extraction` | `cheapest_provider` | 1 | 0.949 | 0.0068 | 0.112 | 100.00% | 100.00% |
| `structured_extraction` | `current_production_policy` | 1 | 0.9077 | 0.0123 | 0.096 | 100.00% | 100.00% |
| `structured_extraction` | `fastest_provider` | 1 | 0.9077 | 0.0123 | 0.095 | 100.00% | 100.00% |
| `structured_extraction` | `openrouter_like_auto` | 1 | 0.949 | 0.0068 | 0.139 | 100.00% | 100.00% |
| `structured_extraction` | `static_primary_backup` | 1 | 0.9077 | 0.0123 | 0.584 | 100.00% | 100.00% |
| `tool_use` | `cheapest_provider` | 1 | 0.9347 | 0.0087 | 0.088 | 100.00% | 100.00% |
| `tool_use` | `current_production_policy` | 1 | 0.9347 | 0.0087 | 0.109 | 100.00% | 100.00% |
| `tool_use` | `fastest_provider` | 1 | 0.9347 | 0.0087 | 0.055 | 100.00% | 100.00% |
| `tool_use` | `openrouter_like_auto` | 1 | 0.9347 | 0.0087 | 0.601 | 100.00% | 100.00% |
| `tool_use` | `static_primary_backup` | 1 | 0.9347 | 0.0087 | 0.077 | 100.00% | 100.00% |
