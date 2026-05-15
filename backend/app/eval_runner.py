from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from statistics import mean
from typing import Any

from sqlalchemy.orm import Session

from . import crud, models, schemas


DEFAULT_STRATEGIES = [
    "static_primary_backup",
    "cheapest_provider",
    "fastest_provider",
    "openrouter_like_auto",
    "current_production_policy",
]
DEFAULT_BASELINE = "current_production_policy"


@dataclass
class EvalResult:
    example_id: str
    workload_class: str
    strategy: str
    request_id: str
    requested_model: str
    selected_model: str | None
    provider: str
    success: bool
    fallback_used: bool
    schema_valid: bool
    tool_success: bool
    latency_ms: float
    total_cost: float
    total_tokens: int
    score: float
    route_trace: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "example_id": self.example_id,
            "workload_class": self.workload_class,
            "strategy": self.strategy,
            "request_id": self.request_id,
            "requested_model": self.requested_model,
            "selected_model": self.selected_model,
            "provider": self.provider,
            "success": self.success,
            "fallback_used": self.fallback_used,
            "schema_valid": self.schema_valid,
            "tool_success": self.tool_success,
            "latency_ms": round(self.latency_ms, 3),
            "total_cost": round(self.total_cost, 6),
            "total_tokens": self.total_tokens,
            "score": round(self.score, 4),
            "route_trace": self.route_trace,
        }


@dataclass
class PolicyDryRunResult:
    case_id: str
    example_id: str
    strategy: str
    blocked: bool
    block_reason: str | None
    selected_provider: str | None
    selected_model: str | None
    accepted_candidates: int
    rejected_candidates: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "example_id": self.example_id,
            "strategy": self.strategy,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "selected_provider": self.selected_provider,
            "selected_model": self.selected_model,
            "accepted_candidates": self.accepted_candidates,
            "rejected_candidates": self.rejected_candidates,
        }


def load_dataset(dataset_path: str | Path) -> dict[str, Any]:
    with Path(dataset_path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_request_payload(example: dict[str, Any], strategy: str) -> dict[str, Any]:
    payload = {
        "model": example["model"],
        "messages": example["messages"],
    }

    optional_fields = [
        "temperature",
        "top_p",
        "max_tokens",
        "stop",
        "tools",
        "tool_choice",
        "response_format",
    ]
    for field in optional_fields:
        if field in example:
            payload[field] = example[field]

    provider_preferences = dict(example.get("provider", {}))

    if strategy == "cheapest_provider":
        provider_preferences["sort"] = "price"
    elif strategy == "fastest_provider":
        provider_preferences["sort"] = "latency"
    elif strategy == "openrouter_like_auto":
        payload["model"] = "router/auto"
        provider_preferences.setdefault("sort", "balanced")
    elif strategy == "current_production_policy":
        provider_preferences.setdefault("sort", "balanced")
    elif strategy == "static_primary_backup":
        provider_preferences.setdefault("sort", "priority")

    if provider_preferences:
        payload["provider"] = provider_preferences

    return payload


def _score_response(
    example: dict[str, Any],
    response: schemas.ChatCompletionResponse,
    request_log: models.RequestLog | None,
) -> float:
    success_score = 1.0
    schema_score = 1.0 if ("response_format" not in example or response.structured_output is not None) else 0.0
    tool_score = 1.0 if ("tools" not in example or response.tool_calls) else 0.0
    latency_budget = float(example.get("latency_budget_ms") or 1000)
    cost_budget = float(example.get("max_cost_usd") or 0.01)

    latency_ms = request_log.latency if request_log is not None else latency_budget
    cost_amount = request_log.cost_amount if request_log is not None else cost_budget

    latency_score = max(0.0, 1.0 - (latency_ms / max(latency_budget, 1.0)))
    cost_score = max(0.0, 1.0 - (cost_amount / max(cost_budget, 0.000001)))

    return (
        0.35 * success_score
        + 0.2 * schema_score
        + 0.15 * tool_score
        + 0.15 * latency_score
        + 0.15 * cost_score
    )


def run_single_example(
    db: Session,
    example: dict[str, Any],
    strategy: str,
    api_key_label: str = "eval_runner",
) -> EvalResult:
    payload = build_request_payload(example, strategy)
    request = schemas.ChatCompletionRequest.model_validate(payload)
    route_trace = crud.build_route_decision_trace(db=db, request=request)
    try:
        response = crud.create_chat_completion(
            db=db,
            request=request,
            api_key_label=api_key_label,
        )
        request_log = (
            db.query(models.RequestLog)
            .filter(models.RequestLog.request_id == response.request_id)
            .first()
        )
        score = _score_response(example, response, request_log)
        return EvalResult(
            example_id=example["example_id"],
            workload_class=example["workload_class"],
            strategy=strategy,
            request_id=response.request_id,
            requested_model=payload["model"],
            selected_model=response.selected_model,
            provider=response.provider,
            success=True,
            fallback_used=response.fallback_used,
            schema_valid=("response_format" not in example or response.structured_output is not None),
            tool_success=("tools" not in example or bool(response.tool_calls)),
            latency_ms=request_log.latency if request_log is not None else 0.0,
            total_cost=request_log.cost_amount if request_log is not None else 0.0,
            total_tokens=response.usage.total_tokens,
            score=score,
            route_trace=route_trace,
        )
    except ValueError:
        latest_log = (
            db.query(models.RequestLog)
            .order_by(models.RequestLog.id.desc())
            .first()
        )
        return EvalResult(
            example_id=example["example_id"],
            workload_class=example["workload_class"],
            strategy=strategy,
            request_id=latest_log.request_id if latest_log is not None else "failed",
            requested_model=payload["model"],
            selected_model=None,
            provider=route_trace.get("selected_provider") or "none",
            success=False,
            fallback_used=latest_log.fallback_used if latest_log is not None else False,
            schema_valid=False,
            tool_success=False,
            latency_ms=latest_log.latency if latest_log is not None else 0.0,
            total_cost=latest_log.cost_amount if latest_log is not None else 0.0,
            total_tokens=0,
            score=0.0,
            route_trace=route_trace,
        )


def build_decision_highlights(results: list[EvalResult]) -> list[dict[str, Any]]:
    highlights: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in results:
        key = (item.workload_class, item.strategy)
        if key in seen:
            continue
        seen.add(key)
        top_candidates = [
            candidate
            for candidate in item.route_trace.get("candidates", [])
            if candidate.get("accepted")
        ][:2]
        rejected_candidates = [
            {
                "provider": candidate.get("provider"),
                "reject_reason": candidate.get("reject_reason"),
            }
            for candidate in item.route_trace.get("candidates", [])
            if not candidate.get("accepted")
        ][:2]
        highlights.append(
            {
                "workload_class": item.workload_class,
                "strategy": item.strategy,
                "selected_provider": item.route_trace.get("selected_provider"),
                "selected_model": item.route_trace.get("selected_model"),
                "compression_applied": item.route_trace.get("compression", {}).get("applied", False),
                "top_candidates": top_candidates,
                "rejected_candidates": rejected_candidates,
            }
        )
    return highlights


def build_shadow_comparisons(
    results: list[EvalResult],
    baseline_strategy: str,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], EvalResult] = {
        (item.example_id, item.strategy): item
        for item in results
    }
    example_ids = sorted({item.example_id for item in results})
    strategies = sorted({item.strategy for item in results if item.strategy != baseline_strategy})
    comparisons: list[dict[str, Any]] = []
    for example_id in example_ids:
        baseline = grouped.get((example_id, baseline_strategy))
        if baseline is None:
            continue
        for strategy in strategies:
            candidate = grouped.get((example_id, strategy))
            if candidate is None:
                continue
            comparisons.append(
                {
                    "example_id": example_id,
                    "workload_class": candidate.workload_class,
                    "strategy": strategy,
                    "baseline_strategy": baseline_strategy,
                    "score_delta": round(candidate.score - baseline.score, 4),
                    "cost_delta": round(candidate.total_cost - baseline.total_cost, 6),
                    "latency_delta_ms": round(candidate.latency_ms - baseline.latency_ms, 3),
                    "winner": (
                        strategy
                        if (
                            candidate.score > baseline.score
                            or (
                                candidate.score == baseline.score
                                and candidate.total_cost < baseline.total_cost
                            )
                        )
                        else baseline_strategy
                    ),
                }
            )
    return comparisons


def run_policy_dry_runs(
    db: Session,
    dataset: dict[str, Any],
    strategies: list[str],
) -> list[PolicyDryRunResult]:
    examples_by_id = {
        example["example_id"]: example
        for example in dataset.get("examples", [])
    }
    results: list[PolicyDryRunResult] = []
    for case in dataset.get("policy_dry_run_cases", []):
        example = examples_by_id.get(case["example_id"])
        if example is None:
            continue
        for strategy in strategies:
            payload = build_request_payload(example, strategy)
            request = schemas.ChatCompletionRequest.model_validate(payload)
            trace = crud.build_route_decision_trace(
                db=db,
                request=request,
                guardrail_override=case.get("guardrails", {}),
            )
            candidates = trace.get("candidates", [])
            results.append(
                PolicyDryRunResult(
                    case_id=case["case_id"],
                    example_id=case["example_id"],
                    strategy=strategy,
                    blocked=trace.get("blocked", False),
                    block_reason=trace.get("block_reason"),
                    selected_provider=trace.get("selected_provider"),
                    selected_model=trace.get("selected_model"),
                    accepted_candidates=sum(1 for item in candidates if item.get("accepted")),
                    rejected_candidates=sum(1 for item in candidates if not item.get("accepted")),
                )
            )
    return results


def aggregate_results(results: list[EvalResult]) -> list[dict[str, Any]]:
    grouped: dict[str, list[EvalResult]] = {}
    for item in results:
        grouped.setdefault(item.strategy, []).append(item)

    summary: list[dict[str, Any]] = []
    for strategy, items in sorted(grouped.items()):
        summary.append(
            {
                "strategy": strategy,
                "requests": len(items),
                "success_rate": round(sum(1 for item in items if item.success) / len(items), 4),
                "schema_valid_rate": round(sum(1 for item in items if item.schema_valid) / len(items), 4),
                "tool_success_rate": round(sum(1 for item in items if item.tool_success) / len(items), 4),
                "failure_rate": round(sum(1 for item in items if not item.success) / len(items), 4),
                "avg_latency_ms": round(mean(item.latency_ms for item in items), 3),
                "avg_total_cost": round(mean(item.total_cost for item in items), 6),
                "avg_score": round(mean(item.score for item in items), 4),
            }
        )
    return summary


def aggregate_results_by_workload(results: list[EvalResult]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[EvalResult]] = {}
    for item in results:
        grouped.setdefault((item.workload_class, item.strategy), []).append(item)

    summary: list[dict[str, Any]] = []
    for (workload_class, strategy), items in sorted(grouped.items()):
        summary.append(
            {
                "workload_class": workload_class,
                "strategy": strategy,
                "requests": len(items),
                "success_rate": round(sum(1 for item in items if item.success) / len(items), 4),
                "schema_valid_rate": round(sum(1 for item in items if item.schema_valid) / len(items), 4),
                "tool_success_rate": round(sum(1 for item in items if item.tool_success) / len(items), 4),
                "failure_rate": round(sum(1 for item in items if not item.success) / len(items), 4),
                "avg_latency_ms": round(mean(item.latency_ms for item in items), 3),
                "avg_total_cost": round(mean(item.total_cost for item in items), 6),
                "avg_score": round(mean(item.score for item in items), 4),
            }
        )
    return summary


def compute_baseline_deltas(
    summary: list[dict[str, Any]],
    baseline_strategy: str,
) -> list[dict[str, Any]]:
    by_strategy = {item["strategy"]: item for item in summary}
    baseline = by_strategy.get(baseline_strategy)
    if baseline is None:
        return summary

    enhanced: list[dict[str, Any]] = []
    baseline_cost = baseline["avg_total_cost"]
    baseline_score = baseline["avg_score"]
    baseline_latency = baseline["avg_latency_ms"]
    for item in summary:
        enhanced.append(
            {
                **item,
                "score_delta_vs_baseline": round(item["avg_score"] - baseline_score, 4),
                "cost_delta_vs_baseline": round(item["avg_total_cost"] - baseline_cost, 6),
                "latency_delta_vs_baseline": round(item["avg_latency_ms"] - baseline_latency, 3),
            }
        )
    return enhanced


def compute_workload_winners(workload_summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in workload_summary:
        grouped.setdefault(item["workload_class"], []).append(item)

    winners: list[dict[str, Any]] = []
    for workload_class, rows in sorted(grouped.items()):
        best = sorted(
            rows,
            key=lambda row: (-row["avg_score"], row["avg_total_cost"], row["avg_latency_ms"]),
        )[0]
        winners.append(
            {
                "workload_class": workload_class,
                "winner_strategy": best["strategy"],
                "winner_score": best["avg_score"],
                "winner_cost": best["avg_total_cost"],
                "winner_latency_ms": best["avg_latency_ms"],
            }
        )
    return winners


def render_markdown_report(
    dataset_name: str,
    strategies: list[str],
    summary: list[dict[str, Any]],
    workload_summary: list[dict[str, Any]] | None = None,
    workload_winners: list[dict[str, Any]] | None = None,
    decision_highlights: list[dict[str, Any]] | None = None,
    shadow_comparisons: list[dict[str, Any]] | None = None,
    policy_dry_runs: list[dict[str, Any]] | None = None,
) -> str:
    lines = [
        f"# Eval Report: {dataset_name}",
        "",
        "## Strategies",
        "",
    ]
    for strategy in strategies:
        lines.append(f"- `{strategy}`")
    lines.extend(
        [
            "",
            "## Summary",
            "",
            "| Strategy | Requests | Success Rate | Failure Rate | Schema Rate | Tool Rate | Avg Latency (ms) | Avg Cost | Avg Score | Score vs Baseline | Cost vs Baseline |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in summary:
        lines.append(
            f"| `{item['strategy']}` | {item['requests']} | {item['success_rate']:.2%} | {item['failure_rate']:.2%} | "
            f"{item['schema_valid_rate']:.2%} | {item['tool_success_rate']:.2%} | "
            f"{item['avg_latency_ms']} | {item['avg_total_cost']} | {item['avg_score']} | "
            f"{item.get('score_delta_vs_baseline', 0.0)} | {item.get('cost_delta_vs_baseline', 0.0)} |"
        )
    if workload_winners:
        lines.extend(
            [
                "",
                "## Workload Winners",
                "",
                "| Workload | Winner Strategy | Winner Score | Winner Cost | Winner Latency (ms) |",
                "| --- | --- | ---: | ---: | ---: |",
            ]
        )
        for item in workload_winners:
            lines.append(
                f"| `{item['workload_class']}` | `{item['winner_strategy']}` | "
                f"{item['winner_score']} | {item['winner_cost']} | {item['winner_latency_ms']} |"
            )
    if workload_summary:
        lines.extend(
            [
                "",
                "## Workload Breakdown",
                "",
                "| Workload | Strategy | Requests | Avg Score | Avg Cost | Avg Latency (ms) | Failure Rate | Schema Rate | Tool Rate |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in workload_summary:
            lines.append(
                f"| `{item['workload_class']}` | `{item['strategy']}` | {item['requests']} | "
                f"{item['avg_score']} | {item['avg_total_cost']} | {item['avg_latency_ms']} | {item['failure_rate']:.2%} | "
                f"{item['schema_valid_rate']:.2%} | {item['tool_success_rate']:.2%} |"
            )
    if decision_highlights:
        lines.extend(
            [
                "",
                "## Decision Highlights",
                "",
            ]
        )
        for item in decision_highlights:
            lines.append(f"### `{item['workload_class']}` / `{item['strategy']}`")
            lines.append(f"- Selected provider: `{item['selected_provider']}`")
            lines.append(f"- Selected model: `{item['selected_model']}`")
            lines.append(f"- Compression applied: `{item['compression_applied']}`")
            if item["top_candidates"]:
                for candidate in item["top_candidates"]:
                    lines.append(
                        f"- Accepted candidate: `{candidate['provider']}` price={candidate['total_price_per_1k']} "
                        f"latency={candidate['avg_latency_ms']} capabilities={','.join(candidate['capabilities'])}"
                    )
            if item["rejected_candidates"]:
                for candidate in item["rejected_candidates"]:
                    lines.append(
                        f"- Rejected candidate: `{candidate['provider']}` reason=`{candidate['reject_reason']}`"
                    )
            lines.append("")
    if shadow_comparisons:
        lines.extend(
            [
                "",
                "## Shadow Comparisons",
                "",
                "| Example | Workload | Strategy | Score Delta | Cost Delta | Latency Delta (ms) | Winner |",
                "| --- | --- | --- | ---: | ---: | ---: | --- |",
            ]
        )
        for item in shadow_comparisons:
            lines.append(
                f"| `{item['example_id']}` | `{item['workload_class']}` | `{item['strategy']}` | "
                f"{item['score_delta']} | {item['cost_delta']} | {item['latency_delta_ms']} | `{item['winner']}` |"
            )
    if policy_dry_runs:
        lines.extend(
            [
                "",
                "## Policy Dry Run",
                "",
                "| Case | Example | Strategy | Blocked | Block Reason | Selected Provider | Accepted Candidates | Rejected Candidates |",
                "| --- | --- | --- | --- | --- | --- | ---: | ---: |",
            ]
        )
        for item in policy_dry_runs:
            lines.append(
                f"| `{item['case_id']}` | `{item['example_id']}` | `{item['strategy']}` | "
                f"`{item['blocked']}` | `{item['block_reason']}` | `{item['selected_provider']}` | "
                f"{item['accepted_candidates']} | {item['rejected_candidates']} |"
            )
    lines.append("")
    return "\n".join(lines)
