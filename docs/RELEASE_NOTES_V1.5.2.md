# Goku-Router v1.5.2 Release Notes

## Highlights

- Added an admin LLM quality evaluation tool.
- Added a new `/admin/quality-evals/run` API for deterministic model-quality checks.
- Added a React admin page under Routing for running manual quality evals.

## Quality Evaluation

The new evaluator can run a set of cases against a selected model/provider mapping and returns:

- average score and pass count
- per-case completion output
- keyword matches and missing terms
- forbidden term hits
- JSON / structured-output validity signal
- tool-call success signal
- latency, token usage, and estimated cost

The scoring is deterministic and uses objective signals, so it can run cheaply without a judge model. It is designed so an LLM-as-judge signal can be added later.

## Validation

- `PYTHONPATH=backend pytest backend/tests/test_quality_eval_api.py -q`
- `npm run typecheck`
