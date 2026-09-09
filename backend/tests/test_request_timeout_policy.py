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

    # 300s，不是 180s：2701d2a 把 tool_use 这一档从 180000 提到 300000，与
    # goku-core 自己的 LLM_TIMEOUT 对齐。classify_workload 对任何带 tools 的请求
    # 都返回 tool_use，也就是整个 ReAct 循环走的都是这一档，而它此前是最短的一档
    # —— 实测有一步跑了 182.0s 撞上 180s 上限，返回「The read operation timed out」，
    # 读起来像故障，其实只是闸门设得太低。
    #
    # 那次改动漏了这条断言，套件红了三天。断言值跟随 config.request_type_timeout_ms
    # 的默认值走；要改超时策略，改那里，这里同步。
    assert effective == 300000
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
