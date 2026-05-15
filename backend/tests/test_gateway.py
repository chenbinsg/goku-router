from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
AUTH_HEADERS = {"Authorization": "Bearer demo-router-key"}


def test_list_models_returns_seeded_catalog():
    response = client.get("/v1/models", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.json()["models"] == ["model1", "model2", "router/auto"]


def test_chat_completion_uses_primary_provider():
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "model1",
            "messages": [{"role": "user", "content": "Hello router primary unique"}],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "provider_primary"
    assert payload["fallback_used"] is False
    assert payload["usage"]["total_tokens"] > 0
    assert "cache_hit" in payload


def test_chat_completion_falls_back_to_backup_provider():
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "model1",
            "messages": [{"role": "user", "content": "[fail:provider_primary] switch"}],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "provider_backup"
    assert payload["fallback_used"] is True


def test_chat_completion_streams_chunks_and_usage():
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "model1",
            "stream": True,
            "messages": [{"role": "user", "content": "Hello stream"}],
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "chat.completion.chunk" in body
    assert '"usage"' in body
    assert "data: [DONE]" in body


def test_chat_completion_honors_request_level_provider_order_without_fallback():
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "model1",
            "messages": [{"role": "user", "content": "Hello preferred provider"}],
            "provider": {
                "order": ["provider_backup", "provider_primary"],
                "allow_fallbacks": False,
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "provider_backup"
    assert payload["fallback_used"] is False


def test_chat_completion_hits_prompt_cache_on_second_request():
    request_payload = {
        "model": "model1",
        "messages": [{"role": "user", "content": "Cache this prompt"}],
    }
    first_response = client.post("/v1/chat/completions", headers=AUTH_HEADERS, json=request_payload)
    assert first_response.status_code == 200
    second_response = client.post("/v1/chat/completions", headers=AUTH_HEADERS, json=request_payload)
    assert second_response.status_code == 200
    payload = second_response.json()
    assert payload["cache_hit"] is True
    assert payload["usage"]["cached_tokens"] > 0


def test_sticky_routing_prefers_previous_provider_for_same_sticky_key():
    first_response = client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "model1",
            "messages": [{"role": "user", "content": "Sticky route warmup"}],
            "provider": {
                "order": ["provider_backup", "provider_primary"],
                "allow_fallbacks": False,
                "sticky_key": "conversation-001",
            },
        },
    )
    assert first_response.status_code == 200
    assert first_response.json()["provider"] == "provider_backup"

    second_response = client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "model1",
            "messages": [{"role": "user", "content": "Sticky route next turn"}],
            "provider": {
                "sticky_key": "conversation-001",
            },
        },
    )
    assert second_response.status_code == 200
    assert second_response.json()["provider"] == "provider_backup"


def test_router_auto_prefers_cheaper_provider():
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "router/auto",
            "messages": [{"role": "user", "content": "Pick the best route"}],
            "provider": {"sort": "price"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "provider_backup"
    assert payload["selected_model"] in {"model1", "model2"}


def test_router_auto_honors_zdr_requirement():
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "router/auto",
            "messages": [{"role": "user", "content": "Handle a ZDR request"}],
            "provider": {"zdr": True},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "provider_primary"


def test_router_auto_honors_data_collection_deny():
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "router/auto",
            "messages": [{"role": "user", "content": "Privacy sensitive route"}],
            "provider": {"sort": "price", "data_collection": "deny"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "provider_primary"


def test_router_auto_requires_parameter_support():
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "router/auto",
            "messages": [{"role": "user", "content": "Use a tool and keep parameter support strict"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup_weather",
                        "description": "Get weather",
                        "parameters": {"type": "object"},
                    },
                }
            ],
            "provider": {"require_parameters": True},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "provider_primary"


def test_router_auto_rejects_provider_when_prompt_tokens_exceed_limit():
    update_response = client.put(
        "/admin/guardrails",
        json={
            "allowed_providers": [],
            "denied_providers": [],
            "blocked_words": [],
            "max_prompt_chars": 50000,
            "retention_mode": "standard",
        },
    )
    assert update_response.status_code == 200
    long_prompt = (f"{uuid4()} " + ("token " * 3000)).strip()
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "router/auto",
            "messages": [{"role": "user", "content": long_prompt}],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "provider_primary"
    logs_response = client.get("/admin/logs")
    trace = logs_response.json()[0]["route_trace"]
    rejected = [item for item in trace["candidates"] if item["provider"] == "provider_backup"][0]
    assert rejected["reject_reason"] == "prompt_tokens_above_provider_limit"


def test_router_auto_rejects_provider_when_output_tokens_exceed_limit():
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "router/auto",
            "messages": [{"role": "user", "content": "Need a long answer"}],
            "max_tokens": 3000,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "provider_primary"
    logs_response = client.get("/admin/logs")
    trace = logs_response.json()[0]["route_trace"]
    rejected = [item for item in trace["candidates"] if item["provider"] == "provider_backup"][0]
    assert rejected["reject_reason"] == "max_output_tokens_above_provider_limit"


def test_structured_output_json_schema_is_returned():
    unique_prompt = f"Summarize this as JSON {uuid4()}"
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "model1",
            "messages": [{"role": "user", "content": unique_prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string"},
                            "token_count": {"type": "integer"},
                        },
                        "required": ["summary", "token_count"],
                    }
                },
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["structured_output"]["summary"]
    assert isinstance(payload["structured_output"]["token_count"], int)
    assert payload["response_healed"] is True
    assert payload["healing_strategy"] == "json_schema_repair"


def test_structured_output_json_object_is_healed_when_provider_returns_text():
    unique_prompt = f"Return JSON object {uuid4()}"
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "model1",
            "messages": [{"role": "user", "content": unique_prompt}],
            "response_format": {
                "type": "json_object",
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["response_healed"] is True
    assert payload["healing_strategy"] == "json_object_wrap"
    assert payload["structured_output"]["answer"]


def test_tool_calling_is_returned_from_mock_provider():
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "model1",
            "messages": [{"role": "user", "content": "Use the weather tool"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup_weather",
                        "description": "Get weather",
                        "parameters": {"type": "object"},
                    },
                }
            ],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["tool_calls"][0]["function"]["name"] == "lookup_weather"


def test_guardrails_block_banned_words():
    update_response = client.put(
        "/admin/guardrails",
        json={
            "allowed_providers": [],
            "denied_providers": [],
            "blocked_words": ["forbidden"],
            "max_prompt_chars": 4000,
            "retention_mode": "standard",
        },
    )
    assert update_response.status_code == 200

    response = client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "model1",
            "messages": [{"role": "user", "content": "This is forbidden"}],
        },
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "GUARDRAIL_BLOCKED_WORD"


def test_analytics_summary_returns_breakdowns():
    client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "model1",
            "messages": [{"role": "user", "content": "analytics health"}],
        },
    )
    client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "model1",
            "messages": [{"role": "user", "content": "analytics cost backup"}],
            "provider": {
                "order": ["provider_backup", "provider_primary"],
                "allow_fallbacks": False,
            },
        },
    )
    response = client.get("/admin/analytics/summary")
    assert response.status_code == 200
    payload = response.json()
    assert "provider_breakdown" in payload
    assert "model_breakdown" in payload
    assert "route_scoring_profile_name" in payload
    assert "recent_route_change_rate" in payload
    assert "cost_optimization_opportunities" in payload
    assert "anomaly_alerts" in payload
    assert "route_scoring_drift" in payload
    assert isinstance(payload["cost_optimization_opportunities"], list)
    assert isinstance(payload["anomaly_alerts"], list)
    assert isinstance(payload["route_scoring_drift"], list)
    assert any(item["category"] == "provider_shift" for item in payload["cost_optimization_opportunities"])


def test_detect_anomaly_notifications_creates_notifications():
    client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "model1",
            "messages": [{"role": "user", "content": "[fail:provider_primary] anomaly one"}],
        },
    )
    client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "model1",
            "messages": [{"role": "user", "content": "[fail:provider_primary] anomaly two"}],
        },
    )
    response = client.post("/admin/notifications/detect-anomalies")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    if payload:
        assert payload[0]["type"].startswith("anomaly_")


def test_policy_dry_run_returns_block_when_provider_is_denied():
    response = client.post(
        "/admin/guardrails/dry-run",
        json={
            "model": "model1",
            "messages": [{"role": "user", "content": "Extract finance risk data"}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "schema": {
                        "type": "object",
                        "properties": {"risk": {"type": "string"}},
                        "required": ["risk"],
                    }
                },
            },
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
    assert payload["blocked"] is False
    assert payload["selected_provider"] == "provider_backup"
    assert "policy_diff" in payload
    assert "eligibility_summary" in payload


def test_policy_dry_run_reports_zdr_rejection_reason():
    response = client.post(
        "/admin/guardrails/dry-run",
        json={
            "model": "router/auto",
            "messages": [{"role": "user", "content": "Need privacy preserved"}],
            "provider": {
                "zdr": True,
                "order": ["provider_backup", "provider_primary"],
            },
            "guardrails": {
                "allowed_providers": [],
                "denied_providers": [],
                "blocked_words": [],
                "max_prompt_chars": 4000,
                "retention_mode": "standard",
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    rejected = [item for item in payload["route_trace"]["candidates"] if item["provider"] == "provider_backup"][0]
    assert rejected["reject_reason"] == "zdr_not_supported"
    assert payload["eligibility_summary"]["zdr_not_supported"] >= 1


def test_router_auto_classifies_multimodal_and_picks_capable_provider():
    response = client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "router/auto",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Read this dashboard image"},
                        {"type": "image_url", "image_url": {"url": "https://example.com/demo.png"}},
                    ],
                }
            ],
            "provider": {"require_capabilities": ["multimodal"]},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "provider_primary"


def test_route_scoring_replay_returns_recent_log_comparison():
    seed_response = client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "model1",
            "messages": [{"role": "user", "content": "Replay this route"}],
        },
    )
    assert seed_response.status_code == 200

    replay_response = client.post(
        "/admin/router-scoring/replay",
        json={
            "source": "recent_logs",
            "limit": 5,
        },
    )
    assert replay_response.status_code == 200
    payload = replay_response.json()
    assert payload["source"] == "recent_logs"
    assert payload["total_cases"] >= 1
    assert payload["items"][0]["workload_class"]


def test_route_scoring_experiment_can_route_requests_and_log_variant():
    unique_suffix = uuid4().hex
    train_response = client.post(
        "/admin/router-scoring/train",
        json={
            "dataset_path": "backend/evals/datasets/sample_workloads.json",
            "profile_name": f"exp_profile_{uuid4()}",
            "baseline_strategy": "current_production_policy",
        },
    )
    assert train_response.status_code == 200
    challenger_profile_name = train_response.json()["name"]

    create_response = client.post(
        "/admin/router-scoring/experiments",
        json={
            "name": f"experiment_{uuid4()}",
            "control_profile_name": "default_heuristic_profile",
            "challenger_profile_name": challenger_profile_name,
            "traffic_percentage": 100,
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    experiment_name = create_response.json()["name"]

    response = client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "router/auto",
            "messages": [{"role": "user", "content": f"Experiment route this request {unique_suffix}"}],
            "provider": {
                "sticky_key": f"experiment-user-{unique_suffix}",
            },
        },
    )
    assert response.status_code == 200

    logs_response = client.get("/admin/logs")
    assert logs_response.status_code == 200
    matching_log = next(item for item in logs_response.json() if item["request_id"] == response.json()["request_id"])
    assert matching_log["experiment_name"] == experiment_name
    assert matching_log["experiment_variant"] == "challenger"
    assert matching_log["applied_profile_name"] == challenger_profile_name

    analytics_response = client.get("/admin/analytics/summary")
    assert analytics_response.status_code == 200
    experiment_summaries = analytics_response.json()["route_scoring_experiments"]
    assert any(item["name"] == experiment_name and item["variant"] == "challenger" for item in experiment_summaries)


def test_route_scoring_recalibration_from_logs_returns_active_profile():
    client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "router/auto",
            "messages": [{"role": "user", "content": "Feedback calibration request one"}],
            "provider": {"sort": "price"},
        },
    )
    client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "model1",
            "messages": [{"role": "user", "content": "Feedback calibration request two"}],
            "provider": {"order": ["provider_backup", "provider_primary"], "allow_fallbacks": False},
        },
    )

    recalibrate_response = client.post(
        "/admin/router-scoring/recalibrate",
        json={
            "profile_name": f"feedback_profile_{uuid4()}",
            "limit": 50,
        },
    )
    assert recalibrate_response.status_code == 200
    payload = recalibrate_response.json()
    assert payload["status"] == "active"
    assert payload["source_summary"]["considered_requests"] >= 1
    assert "calibration_summary" in payload
    follow_up = client.get("/admin/router-scoring/profile")
    assert follow_up.status_code == 200
    assert follow_up.json()["name"] == payload["name"]


def test_route_scoring_replay_supports_workspace_filters():
    seed_response = client.get("/v1/models", headers=AUTH_HEADERS)
    assert seed_response.status_code == 200
    organizations_response = client.get("/admin/organizations")
    projects_response = client.get("/admin/projects")
    organization_id = next(item["id"] for item in organizations_response.json() if item["name"] == "Demo Org")
    project_id = next(item["id"] for item in projects_response.json() if item["name"] == "Demo Project")

    api_key_response = client.post(
        "/admin/router-api-keys",
        json={
            "name": f"workspace-replay-key-{uuid4()}",
            "organization_id": organization_id,
            "project_id": project_id,
        },
    )
    assert api_key_response.status_code == 200
    workspace_key = api_key_response.json()["plain_api_key"]

    workspace_response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {workspace_key}"},
        json={
            "model": "model1",
            "messages": [{"role": "user", "content": "Replay scoped workspace route"}],
        },
    )
    assert workspace_response.status_code == 200

    replay_response = client.post(
        "/admin/router-scoring/replay",
        json={
            "source": "recent_logs",
            "limit": 10,
            "organization_id": organization_id,
            "project_id": project_id,
        },
    )
    assert replay_response.status_code == 200
    payload = replay_response.json()
    assert payload["source"] == "recent_logs"
    assert f"org={organization_id}:proj={project_id}" in payload["source_label"]
    assert payload["total_cases"] >= 1
    assert any(item["request_id"] for item in payload["items"])


def test_route_scoring_replay_supports_profile_vs_profile_comparison():
    profile_a_response = client.post(
        "/admin/router-scoring/train",
        json={
            "dataset_path": "backend/evals/datasets/sample_workloads.json",
            "profile_name": f"profile_a_{uuid4()}",
            "baseline_strategy": "current_production_policy",
        },
    )
    assert profile_a_response.status_code == 200
    profile_a = profile_a_response.json()["name"]

    profile_b_response = client.post(
        "/admin/router-scoring/recalibrate",
        json={
            "profile_name": f"profile_b_{uuid4()}",
            "limit": 50,
        },
    )
    assert profile_b_response.status_code == 200
    profile_b = profile_b_response.json()["name"]

    replay_response = client.post(
        "/admin/router-scoring/replay",
        json={
            "source": "dataset",
            "dataset_path": "backend/evals/datasets/sample_workloads.json",
            "strategy": "current_production_policy",
            "limit": 5,
            "baseline_profile_name": profile_a,
            "comparison_profile_name": profile_b,
        },
    )
    assert replay_response.status_code == 200
    payload = replay_response.json()
    assert f"{profile_a}_vs_{profile_b}" in payload["source_label"]
    assert payload["total_cases"] >= 1
    assert payload["items"][0]["baseline_profile_name"] == profile_a
    assert payload["items"][0]["comparison_profile_name"] == profile_b


def test_route_scoring_replay_export_returns_download_artifact():
    response = client.post(
        "/admin/router-scoring/replay/export",
        json={
            "source": "dataset",
            "dataset_path": "backend/evals/datasets/sample_workloads.json",
            "strategy": "current_production_policy",
            "limit": 5,
            "baseline_profile_name": "default_heuristic_profile",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["file_name"].startswith("route_replay_")
    assert payload["download_url"].startswith("data:text/markdown")


def test_request_logs_include_route_scoring_metadata():
    client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "model1",
            "messages": [{"role": "user", "content": "log metadata"}],
        },
    )
    response = client.get("/admin/logs")
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["workload_class"]
    assert "applied_profile_name" in payload[0]
    assert "route_changed" in payload[0]
    assert "cache_hit" in payload[0]
    assert "response_healed" in payload[0]
    assert "healing_strategy" in payload[0]


def test_workspace_route_default_applies_price_sort_for_named_scope():
    seed_response = client.get("/v1/models", headers=AUTH_HEADERS)
    assert seed_response.status_code == 200
    organizations_response = client.get("/admin/organizations")
    projects_response = client.get("/admin/projects")
    organization_id = next(item["id"] for item in organizations_response.json() if item["name"] == "Demo Org")
    project_id = next(item["id"] for item in projects_response.json() if item["name"] == "Demo Project")
    create_default_response = client.post(
        "/admin/workspace-route-defaults",
        json={
            "organization_id": organization_id,
            "project_id": project_id,
            "sort_mode": "price",
            "provider_order": [],
            "require_capabilities": [],
            "require_parameters": False,
        },
    )
    assert create_default_response.status_code == 200

    response = client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "router/auto",
            "messages": [{"role": "user", "content": "Use workspace default routing"}],
            "provider": {
                "organization": "Demo Org",
                "project": "Demo Project",
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "provider_backup"

    logs_response = client.get("/admin/logs")
    assert logs_response.status_code == 200
    trace = logs_response.json()[0]["route_trace"]
    assert trace["workspace_default"]["sort_mode"] == "price"
    assert "sort" in trace["workspace_default"]["applied_fields"]


def test_workspace_route_default_can_be_overridden_by_request_sort():
    organizations_response = client.get("/admin/organizations")
    projects_response = client.get("/admin/projects")
    organization_id = next(item["id"] for item in organizations_response.json() if item["name"] == "Demo Org")
    project_id = next(item["id"] for item in projects_response.json() if item["name"] == "Demo Project")
    neutral_guardrail_response = client.post(
        "/admin/workspace-guardrails",
        json={
            "organization_id": organization_id,
            "project_id": project_id,
            "allowed_providers": [],
            "denied_providers": [],
            "blocked_words": [],
            "max_prompt_chars": 4000,
            "retention_mode": "standard",
        },
    )
    assert neutral_guardrail_response.status_code == 200

    response = client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "router/auto",
            "messages": [{"role": "user", "content": "Override workspace default routing"}],
            "provider": {
                "organization": "Demo Org",
                "project": "Demo Project",
                "sort": "latency",
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "provider_primary"


def test_workspace_guardrail_config_can_be_listed_and_updated():
    seed_response = client.get("/v1/models", headers=AUTH_HEADERS)
    assert seed_response.status_code == 200
    organizations_response = client.get("/admin/organizations")
    projects_response = client.get("/admin/projects")
    organization_id = next(item["id"] for item in organizations_response.json() if item["name"] == "Demo Org")
    project_id = next(item["id"] for item in projects_response.json() if item["name"] == "Demo Project")

    create_response = client.post(
        "/admin/workspace-guardrails",
        json={
            "organization_id": organization_id,
            "project_id": project_id,
            "allowed_providers": ["provider_primary"],
            "denied_providers": ["provider_backup"],
            "blocked_words": ["finance-secret"],
            "max_prompt_chars": 250,
            "retention_mode": "zdr",
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["organization_id"] == organization_id
    assert created["project_id"] == project_id
    assert created["denied_providers"] == ["provider_backup"]

    list_response = client.get("/admin/workspace-guardrails")
    assert list_response.status_code == 200
    assert any(item["id"] == created["id"] for item in list_response.json())

    update_response = client.put(
        f"/admin/workspace-guardrails/{created['id']}",
        json={
            "organization_id": organization_id,
            "project_id": project_id,
            "allowed_providers": ["provider_primary"],
            "denied_providers": ["provider_backup"],
            "blocked_words": ["finance-secret", "restricted"],
            "max_prompt_chars": 180,
            "retention_mode": "strict",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["blocked_words"] == ["finance-secret", "restricted"]
    assert updated["max_prompt_chars"] == 180
    assert updated["retention_mode"] == "strict"


def test_workspace_guardrail_applies_to_scoped_requests():
    seed_response = client.get("/v1/models", headers=AUTH_HEADERS)
    assert seed_response.status_code == 200
    organizations_response = client.get("/admin/organizations")
    projects_response = client.get("/admin/projects")
    organization_id = next(item["id"] for item in organizations_response.json() if item["name"] == "Demo Org")
    project_id = next(item["id"] for item in projects_response.json() if item["name"] == "Demo Project")

    create_response = client.post(
        "/admin/workspace-guardrails",
        json={
            "organization_id": organization_id,
            "project_id": project_id,
            "denied_providers": ["provider_primary"],
            "max_prompt_chars": 80,
            "retention_mode": "zdr",
        },
    )
    assert create_response.status_code == 200

    response = client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "router/auto",
            "messages": [{"role": "user", "content": "Use workspace guardrail routing for this scoped request"}],
            "provider": {
                "organization": "Demo Org",
                "project": "Demo Project",
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "provider_backup"

    logs_response = client.get("/admin/logs")
    assert logs_response.status_code == 200
    trace = logs_response.json()[0]["route_trace"]
    assert trace["workspace_guardrails"]["organization_id"] == organization_id
    assert trace["workspace_guardrails"]["project_id"] == project_id
    assert "denied_providers" in trace["workspace_guardrails"]["applied_fields"]
    assert "max_prompt_chars" in trace["workspace_guardrails"]["applied_fields"]
    candidate_reasons = [item.get("reject_reason") for item in trace["candidates"]]
    assert "provider_denied_by_guardrail" in candidate_reasons


def test_workspace_observability_filters_logs_billing_and_analytics():
    seed_response = client.get("/v1/models", headers=AUTH_HEADERS)
    assert seed_response.status_code == 200
    organizations_response = client.get("/admin/organizations")
    projects_response = client.get("/admin/projects")
    organization_id = next(item["id"] for item in organizations_response.json() if item["name"] == "Demo Org")
    project_id = next(item["id"] for item in projects_response.json() if item["name"] == "Demo Project")

    api_key_response = client.post(
        "/admin/router-api-keys",
        json={
            "name": f"workspace-filter-key-{uuid4()}",
            "organization_id": organization_id,
            "project_id": project_id,
        },
    )
    assert api_key_response.status_code == 200
    workspace_key = api_key_response.json()["plain_api_key"]
    workspace_key_name = api_key_response.json()["name"]

    workspace_response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {workspace_key}"},
        json={
            "model": "model1",
            "messages": [{"role": "user", "content": "Scoped workspace request"}],
        },
    )
    assert workspace_response.status_code == 200

    logs_response = client.get(f"/admin/logs?organization_id={organization_id}&project_id={project_id}")
    assert logs_response.status_code == 200
    logs_payload = logs_response.json()
    assert any(item["api_key_label"] == workspace_key_name for item in logs_payload)

    billing_response = client.get(f"/admin/billing/usage?organization_id={organization_id}&project_id={project_id}")
    assert billing_response.status_code == 200
    billing_payload = billing_response.json()["items"]
    assert any(item["api_key_label"] == workspace_key_name for item in billing_payload)

    analytics_response = client.get(f"/admin/analytics/summary?organization_id={organization_id}&project_id={project_id}")
    assert analytics_response.status_code == 200
    analytics_payload = analytics_response.json()
    assert analytics_payload["total_requests"] >= 1
    assert len(analytics_payload["workspace_usage_summary"]) >= 1


def test_environment_filters_logs_billing_and_analytics():
    organizations_response = client.get("/admin/organizations")
    projects_response = client.get("/admin/projects")
    organization_id = next(item["id"] for item in organizations_response.json() if item["name"] == "Demo Org")
    project_id = next(item["id"] for item in projects_response.json() if item["name"] == "Demo Project")

    prod_key_response = client.post(
        "/admin/router-api-keys",
        json={
            "name": f"env-prod-key-{uuid4()}",
            "organization_id": organization_id,
            "project_id": project_id,
            "environment": "prod",
        },
    )
    staging_key_response = client.post(
        "/admin/router-api-keys",
        json={
            "name": f"env-staging-key-{uuid4()}",
            "organization_id": organization_id,
            "project_id": project_id,
            "environment": "staging",
        },
    )
    assert prod_key_response.status_code == 200
    assert staging_key_response.status_code == 200

    for key in [prod_key_response.json()["plain_api_key"], staging_key_response.json()["plain_api_key"]]:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": "model1",
                "messages": [{"role": "user", "content": "Environment scoped request"}],
            },
        )
        assert response.status_code == 200

    logs_response = client.get("/admin/logs?organization_id=%s&project_id=%s&environment=prod" % (organization_id, project_id))
    assert logs_response.status_code == 200
    assert all(item["environment"] == "prod" for item in logs_response.json())

    billing_response = client.get("/admin/billing/usage?organization_id=%s&project_id=%s&environment=prod" % (organization_id, project_id))
    assert billing_response.status_code == 200
    assert all(item["environment"] == "prod" for item in billing_response.json()["items"])

    analytics_response = client.get("/admin/analytics/summary?organization_id=%s&project_id=%s&environment=prod" % (organization_id, project_id))
    assert analytics_response.status_code == 200
    workspace_rows = analytics_response.json()["workspace_usage_summary"]
    assert len(workspace_rows) >= 1
    assert all(item["environment"] == "prod" for item in workspace_rows)


def test_batch_policy_dry_run_returns_strategy_and_diff_summaries():
    response = client.post(
        "/admin/guardrails/dry-run-batch",
        json={
            "dataset_path": "evals/datasets/finance_compliance_pack.json",
            "strategies": ["current_production_policy", "openrouter_like_auto"],
            "workspace_label": "Demo Workspace",
            "guardrails": {
                "allowed_providers": [],
                "denied_providers": ["provider_backup"],
                "blocked_words": [],
                "max_prompt_chars": 4000,
                "retention_mode": "standard",
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["workspace_label"] == "Demo Workspace"
    assert len(payload["strategy_summaries"]) == 2
    assert "policy_diff_summary" in payload


def test_batch_policy_dry_run_export_returns_download_artifact():
    response = client.post(
        "/admin/guardrails/dry-run-batch/export",
        json={
            "dataset_path": "evals/datasets/finance_compliance_pack.json",
            "strategies": ["current_production_policy", "openrouter_like_auto"],
            "workspace_label": "Demo Workspace",
            "guardrails": {
                "allowed_providers": [],
                "denied_providers": [],
                "blocked_words": [],
                "max_prompt_chars": 4000,
                "retention_mode": "standard",
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["file_name"].endswith(".md")
    assert payload["download_url"].startswith("data:text/markdown")


def test_guardrail_policy_presets_can_be_listed_and_updated():
    list_response = client.get("/admin/guardrail-policy-presets")
    assert list_response.status_code == 200
    presets = list_response.json()
    assert any(item["name"] == "balanced_default" for item in presets)

    create_response = client.post(
        "/admin/guardrail-policy-presets",
        json={
            "name": f"ops_guardrail_{uuid4().hex[:8]}",
            "description": "Ops-focused preset",
            "allowed_providers": ["provider_primary"],
            "denied_providers": ["provider_backup"],
            "blocked_words": ["credential"],
            "max_prompt_chars": 1800,
            "retention_mode": "strict",
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["name"].startswith("ops_guardrail_")
    assert created["retention_mode"] == "strict"

    update_response = client.put(
        f"/admin/guardrail-policy-presets/{created['id']}",
        json={
            "name": created["name"],
            "description": "Updated ops preset",
            "allowed_providers": ["provider_primary", "provider_backup"],
            "denied_providers": [],
            "blocked_words": ["credential", "token"],
            "max_prompt_chars": 2200,
            "retention_mode": "standard",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["description"] == "Updated ops preset"
    assert updated["max_prompt_chars"] == 2200
    assert updated["blocked_words"] == ["credential", "token"]


def test_guardrail_policy_compare_returns_summary_and_items():
    response = client.post(
        "/admin/guardrails/preset-compare",
        json={
            "dataset_path": "evals/datasets/finance_compliance_pack.json",
            "strategies": ["current_production_policy", "openrouter_like_auto"],
            "workspace_label": "Demo Workspace",
            "baseline_policy_name": "balanced_default",
            "comparison_policy_name": "finance_strict",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["baseline_policy_name"] == "balanced_default"
    assert payload["comparison_policy_name"] == "finance_strict"
    assert "comparison_summary" in payload
    assert len(payload["items"]) >= 1


def test_guardrail_policy_compare_export_returns_download_artifact():
    response = client.post(
        "/admin/guardrails/preset-compare/export",
        json={
            "dataset_path": "evals/datasets/finance_compliance_pack.json",
            "strategies": ["current_production_policy"],
            "workspace_label": "Demo Workspace",
            "baseline_policy_name": "balanced_default",
            "comparison_policy_name": "finance_strict",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["file_name"].endswith(".md")
    assert payload["download_url"].startswith("data:text/markdown")


def test_router_api_key_supports_environment_expiry_and_rotation():
    created_response = client.post(
        "/admin/router-api-keys",
        json={
            "name": f"enterprise-key-{uuid4().hex[:8]}",
            "environment": "staging",
            "quota_requests": 25,
            "expires_at": "2099-12-31T23:59:59+00:00",
        },
    )
    assert created_response.status_code == 200
    created = created_response.json()
    assert created["environment"] == "staging"
    assert created["expires_at"].startswith("2099-12-31T23:59:59")

    list_response = client.get("/admin/router-api-keys")
    assert list_response.status_code == 200
    listed = next(item for item in list_response.json() if item["id"] == created["id"])
    assert listed["environment"] == "staging"

    rotate_response = client.post(
        f"/admin/router-api-keys/{created['id']}/rotate",
        json={
            "name": f"{created['name']}-v2",
            "quota_requests": 50,
            "expires_at": "2100-01-31T23:59:59+00:00",
        },
    )
    assert rotate_response.status_code == 200
    rotated = rotate_response.json()
    assert rotated["rotated_from_key_id"] == created["id"]
    assert rotated["quota_requests"] == 50
    assert rotated["plain_api_key"].startswith("rk_")

    updated_list_response = client.get("/admin/router-api-keys")
    assert updated_list_response.status_code == 200
    original_row = next(item for item in updated_list_response.json() if item["id"] == created["id"])
    assert original_row["status"] == "rotated"


def test_expired_router_api_key_is_rejected():
    created_response = client.post(
        "/admin/router-api-keys",
        json={
            "name": f"expired-key-{uuid4().hex[:8]}",
            "expires_at": "2000-01-01T00:00:00+00:00",
        },
    )
    assert created_response.status_code == 200
    expired_key = created_response.json()["plain_api_key"]

    response = client.get(
        "/v1/models",
        headers={"Authorization": f"Bearer {expired_key}"},
    )
    assert response.status_code == 401


def test_analytics_export_returns_download_artifact():
    response = client.get("/admin/analytics/export")
    assert response.status_code == 200
    payload = response.json()
    assert payload["file_name"].endswith(".md")
    assert payload["download_url"].startswith("data:text/markdown")


def test_billing_usage_includes_cached_and_reasoning_fields():
    client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "model1",
            "messages": [{"role": "user", "content": "Billing cache prompt"}],
        },
    )
    client.post(
        "/v1/chat/completions",
        headers=AUTH_HEADERS,
        json={
            "model": "model1",
            "messages": [{"role": "user", "content": "Billing cache prompt"}],
        },
    )
    response = client.get("/admin/billing/usage")
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["cached_tokens"] >= 0
    assert payload["items"][0]["reasoning_tokens"] >= 0
    assert "provider_reported_cost" in payload["items"][0]
