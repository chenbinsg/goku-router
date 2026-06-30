from app import schemas
from app import crud


def _request(**kwargs):
    data = {
        "model": "qwen3.6",
        "messages": [schemas.ChatMessage(role="user", content="hello")],
    }
    data.update(kwargs)
    return schemas.ChatCompletionRequest(**data)


def test_route_timeout_is_used_for_normal_chat():
    request = _request()

    effective, trace = crud._resolve_request_timeout_ms(
        request=request,
        workload_class=crud.classify_workload(request),
        route_timeout_ms=90000,
    )

    assert effective == 90000
    assert trace["source"] == "route_rule"
    assert trace["request_type_timeout_ms"] is None


def test_tool_use_raises_timeout_above_route_baseline():
    request = _request(
        tools=[
            schemas.ToolDefinition(
                function={"name": "search", "parameters": {"type": "object"}}
            )
        ],
    )

    effective, trace = crud._resolve_request_timeout_ms(
        request=request,
        workload_class=crud.classify_workload(request),
        route_timeout_ms=90000,
    )

    assert effective == 180000
    assert trace["source"] == "route_rule+request_type"
    assert trace["request_type"] == "tool_use"


def test_explicit_report_timeout_tier_raises_timeout():
    request = _request(metadata={"timeout_tier": "report"})

    effective, trace = crud._resolve_request_timeout_ms(
        request=request,
        workload_class=crud.classify_workload(request),
        route_timeout_ms=90000,
    )

    assert effective == 300000
    assert trace["request_type"] == "report"
    assert trace["timeout_s"] == 300.0


def test_explicit_mcp_alias_uses_mcp_search_timeout():
    request = _request(metadata={"request_type": "mc_search"})

    effective, trace = crud._resolve_request_timeout_ms(
        request=request,
        workload_class=crud.classify_workload(request),
        route_timeout_ms=90000,
    )

    assert effective == 300000
    assert trace["request_type"] == "mcp_search"
