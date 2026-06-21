from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import authenticate_admin_client


client = authenticate_admin_client(TestClient(app))


def test_quality_eval_runs_against_mock_provider():
    suffix = uuid4().hex[:8]
    provider_response = client.post(
        "/admin/providers",
        json={
            "name": f"quality_eval_provider_{suffix}",
            "adapter_type": "mock",
            "status": "active",
            "health_status": "healthy",
            "capabilities": ["chat", "structured_output", "tool_calling"],
            "supported_parameters": ["temperature", "max_tokens", "tools", "response_format"],
        },
    )
    assert provider_response.status_code == 200
    provider = provider_response.json()
    model_response = client.post(
        "/admin/models",
        json={
            "model_id": f"quality-eval-model-{suffix}",
            "provider_id": provider["id"],
            "provider_model_name": "mock-quality-eval-model",
            "status": "active",
        },
    )
    assert model_response.status_code == 200
    model_mapping = model_response.json()

    response = client.post(
        "/admin/quality-evals/run",
        json={
            "name": "smoke_eval",
            "model_id": model_mapping["model_id"],
            "provider_id": provider["id"],
            "cases": [
                {
                    "case_id": "echo-basic",
                    "prompt": "Say hello to the quality evaluator",
                    "expected_contains": ["quality evaluator"],
                    "must_not_contain": ["forbidden-token"],
                    "max_latency_ms": 1000,
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "smoke_eval"
    assert payload["total_cases"] == 1
    assert payload["average_score"] > 0
    assert payload["provider_name"] == provider["name"]
    assert payload["results"][0]["matched_terms"] == ["quality evaluator"]
    assert payload["results"][0]["prompt_tokens"] > 0
