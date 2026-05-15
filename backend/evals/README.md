# Eval Infrastructure

This folder contains the first runnable version of the routing evaluation framework described in [Routing_Eval_Spec.md](/Users/chenbin/router/Routing_Eval_Spec.md:1).

## What it does

The runner executes a dataset of workload examples against multiple routing strategies and outputs:

- per-example result records
- per-strategy aggregate metrics
- a Markdown summary report

## Included strategies

- `static_primary_backup`
- `cheapest_provider`
- `fastest_provider`
- `openrouter_like_auto`
- `current_production_policy`

## Included datasets

- `datasets/sample_workloads.json`
- `datasets/customer_support_pack.json`
- `datasets/sales_ops_agent_pack.json`
- `datasets/finance_compliance_pack.json`

The sample dataset covers:

- general chat
- structured output
- tool use

The customer support pack covers:

- ticket classification
- support summarization
- order-status tool use
- structured extraction for operations workflows

The sales / ops agent pack covers:

- long-context summarization
- agent tool usage
- structured CRM extraction
- multimodal dashboard reading

The finance / compliance pack covers:

- ZDR-like structured extraction requirements
- price-constrained approval classification
- tool calling under stricter capability constraints
- multimodal compliance dashboard review

## Run it

From the repo root:

```bash
cd /Users/chenbin/router/backend
python3 evals/run_eval.py
```

Custom dataset:

```bash
cd /Users/chenbin/router/backend
python3 evals/run_eval.py --dataset evals/datasets/sample_workloads.json
```

Customer-support flavored run:

```bash
cd /Users/chenbin/router/backend
python3 evals/run_eval.py --dataset evals/datasets/customer_support_pack.json
```

Sales / ops agent run:

```bash
cd /Users/chenbin/router/backend
python3 evals/run_eval.py --dataset evals/datasets/sales_ops_agent_pack.json
```

Finance / compliance run:

```bash
cd /Users/chenbin/router/backend
python3 evals/run_eval.py --dataset evals/datasets/finance_compliance_pack.json
```

## Output

The runner writes:

- `backend/evals/results/latest_report.json`
- `backend/evals/results/latest_report.md`

The report now includes:

- overall strategy summary
- deltas vs a baseline strategy
- workload-by-workload breakdown
- per-workload winner summary

## Next upgrades

1. Add OpenRouter-baseline replay input
2. Add shadow-routing export support
3. Add human preference labels
4. Add route decision trace capture
5. Add A/B experiment report format
