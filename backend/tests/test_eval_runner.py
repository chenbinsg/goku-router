from app.eval_runner import (
    aggregate_results,
    aggregate_results_by_workload,
    build_decision_highlights,
    build_shadow_comparisons,
    build_request_payload,
    compute_baseline_deltas,
    compute_workload_winners,
    run_policy_dry_runs,
)
from app.main import app
from fastapi.testclient import TestClient


client = TestClient(app)


def test_build_request_payload_for_openrouter_like_auto():
    payload = build_request_payload(
        {
            "example_id": "1",
            "workload_class": "chat_general",
            "model": "model1",
            "messages": [{"role": "user", "content": "hello"}],
        },
        "openrouter_like_auto",
    )
    assert payload["model"] == "router/auto"
    assert payload["provider"]["sort"] == "balanced"


def test_aggregate_results_summarizes_strategy_rows():
    class FakeResult:
        def __init__(self, strategy, success, schema_valid, tool_success, latency_ms, total_cost, score):
            self.strategy = strategy
            self.success = success
            self.schema_valid = schema_valid
            self.tool_success = tool_success
            self.latency_ms = latency_ms
            self.total_cost = total_cost
            self.score = score

    summary = aggregate_results(
        [
            FakeResult("a", True, True, False, 100, 0.01, 0.8),
            FakeResult("a", True, False, True, 300, 0.03, 0.6),
            FakeResult("b", True, True, True, 200, 0.02, 0.9),
        ]
    )
    assert len(summary) == 2
    assert summary[0]["strategy"] == "a"
    assert summary[0]["requests"] == 2
    assert summary[0]["success_rate"] == 1.0


def test_workload_aggregation_and_winners():
    class FakeResult:
        def __init__(self, workload_class, strategy, success, schema_valid, tool_success, latency_ms, total_cost, score):
            self.workload_class = workload_class
            self.strategy = strategy
            self.success = success
            self.schema_valid = schema_valid
            self.tool_success = tool_success
            self.latency_ms = latency_ms
            self.total_cost = total_cost
            self.score = score

    results = [
        FakeResult("tool_use", "a", True, True, True, 100, 0.01, 0.8),
        FakeResult("tool_use", "b", True, True, True, 150, 0.02, 0.7),
        FakeResult("chat_general", "a", True, True, False, 120, 0.03, 0.6),
    ]
    workload_summary = aggregate_results_by_workload(results)
    assert len(workload_summary) == 3
    winners = compute_workload_winners(workload_summary)
    assert winners[0]["workload_class"] == "chat_general"
    assert winners[1]["winner_strategy"] == "a"


def test_compute_baseline_deltas_adds_delta_fields():
    summary = compute_baseline_deltas(
        [
            {"strategy": "base", "avg_score": 0.8, "avg_total_cost": 0.01, "avg_latency_ms": 100},
            {"strategy": "alt", "avg_score": 0.9, "avg_total_cost": 0.02, "avg_latency_ms": 90},
        ],
        baseline_strategy="base",
    )
    alt = [item for item in summary if item["strategy"] == "alt"][0]
    assert alt["score_delta_vs_baseline"] == 0.1
    assert alt["cost_delta_vs_baseline"] == 0.01


def test_build_decision_highlights_keeps_first_result_per_workload_strategy():
    class FakeResult:
        def __init__(self, workload_class, strategy, route_trace):
            self.workload_class = workload_class
            self.strategy = strategy
            self.route_trace = route_trace

    highlights = build_decision_highlights(
        [
            FakeResult("tool_use", "a", {"selected_provider": "p1", "selected_model": "m1", "compression": {"applied": False}, "candidates": []}),
            FakeResult("tool_use", "a", {"selected_provider": "p2", "selected_model": "m2", "compression": {"applied": True}, "candidates": []}),
        ]
    )
    assert len(highlights) == 1
    assert highlights[0]["selected_provider"] == "p1"


def test_build_shadow_comparisons_compares_against_baseline():
    class FakeResult:
        def __init__(self, example_id, workload_class, strategy, score, total_cost, latency_ms):
            self.example_id = example_id
            self.workload_class = workload_class
            self.strategy = strategy
            self.score = score
            self.total_cost = total_cost
            self.latency_ms = latency_ms

    comparisons = build_shadow_comparisons(
        [
            FakeResult("e1", "chat_general", "current_production_policy", 0.8, 0.02, 100),
            FakeResult("e1", "chat_general", "cheapest_provider", 0.85, 0.01, 120),
        ],
        baseline_strategy="current_production_policy",
    )
    assert len(comparisons) == 1
    assert comparisons[0]["winner"] == "cheapest_provider"
    assert comparisons[0]["score_delta"] == 0.05


def test_run_policy_dry_runs_returns_cases_for_each_strategy():
    dataset = {
        "examples": [
            {
                "example_id": "support_1",
                "workload_class": "chat_general",
                "model": "model1",
                "messages": [{"role": "user", "content": "Hello"}],
            }
        ],
        "policy_dry_run_cases": [
            {
                "case_id": "guardrail_case",
                "example_id": "support_1",
                "guardrails": {
                    "denied_providers": "provider_primary",
                },
            }
        ],
    }
    with TestClient(app) as local_client:
        response = local_client.post(
            "/admin/guardrails/dry-run-batch",
            json={
                "dataset_path": "evals/datasets/sample_workloads.json",
                "strategies": ["current_production_policy"],
                "workspace_label": "Eval Workspace",
                "guardrails": {
                    "allowed_providers": [],
                    "denied_providers": ["provider_primary"],
                    "blocked_words": [],
                    "max_prompt_chars": 4000,
                    "retention_mode": "standard",
                },
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["dataset_name"]
    assert payload["workspace_label"] == "Eval Workspace"
    assert payload["total_cases"] >= 1


def test_router_scoring_profile_training_endpoint_returns_weights():
    response = client.post(
        "/admin/router-scoring/train",
        json={
            "dataset_path": "evals/datasets/sample_workloads.json",
            "profile_name": "test_profile",
            "baseline_strategy": "current_production_policy",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "test_profile"
    assert "chat_general" in payload["weights"]
    assert "calibration_summary" in payload
    follow_up = client.get("/admin/router-scoring/profile")
    assert follow_up.status_code == 200
    assert follow_up.json()["name"] == "test_profile"


def test_router_scoring_replay_endpoint_supports_dataset_mode():
    response = client.post(
        "/admin/router-scoring/replay",
        json={
            "source": "dataset",
            "dataset_path": "backend/evals/datasets/sample_workloads.json",
            "strategy": "current_production_policy",
            "limit": 5,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "dataset"
    assert payload["total_cases"] >= 1
