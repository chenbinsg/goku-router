from app import schemas
from app.models import ModelCatalog, Provider
from app.services import providers


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload
        self.is_success = True
        self.status_code = 200
        self.content = b"{}"

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_openai_compatible_provider_executes_via_httpx(monkeypatch):
    provider = Provider(
        name="external_router",
        adapter_type="openai_compatible",
        status="active",
        health_status="healthy",
        priority=10,
    )
    model = ModelCatalog(
        model_id="router-model",
        provider_id=1,
        provider_model_name="gpt-4.1-mini",
        status="active",
    )
    request = schemas.ChatCompletionRequest(
        model="router-model",
        messages=[schemas.ChatMessage(role="user", content="Hello upstream")],
    )

    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return DummyResponse(
            {
                "choices": [
                    {"message": {"content": "Upstream response"}},
                ],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 7,
                    "cached_tokens": 5,
                    "reasoning_tokens": 2,
                    "cost": 0.0123,
                },
            }
        )

    monkeypatch.setenv(
        "PROVIDER_EXTERNAL_ROUTER_BASE_URL",
        "https://example.test/v1",
    )
    monkeypatch.setenv("PROVIDER_EXTERNAL_ROUTER_API_KEY", "secret-key")
    monkeypatch.setattr(providers.httpx, "post", fake_post)

    result = providers.execute_chat_completion(provider, model, request, timeout_s=42.0)

    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["json"]["model"] == "gpt-4.1-mini"
    assert captured["json"]["messages"][0]["content"] == "Hello upstream"
    assert captured["headers"]["Authorization"] == "Bearer secret-key"
    assert captured["timeout"] == 42.0
    assert result.completion == "Upstream response"
    assert result.prompt_tokens == 12
    assert result.completion_tokens == 7
    assert result.cached_tokens == 5
    assert result.reasoning_tokens == 2
    assert result.provider_reported_cost == 0.0123


def test_openrouter_provider_converts_system_only_prompt_to_user(monkeypatch):
    provider = Provider(
        name="openrouter",
        adapter_type="openai_compatible",
        status="active",
        health_status="healthy",
        priority=10,
    )
    model = ModelCatalog(
        model_id="qwen3.6",
        provider_id=1,
        provider_model_name="Qwen3.6-35B-A3B-FP8",
        status="active",
    )
    request = schemas.ChatCompletionRequest(
        model="qwen3.6",
        messages=[schemas.ChatMessage(role="system", content="Plan the next support action.")],
    )

    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["json"] = json
        return DummyResponse(
            {
                "choices": [
                    {"message": {"content": "Next action planned."}},
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 4,
                },
            }
        )

    monkeypatch.setenv("PROVIDER_OPENROUTER_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("PROVIDER_OPENROUTER_API_KEY", "secret-key")
    monkeypatch.setattr(providers.httpx, "post", fake_post)

    result = providers.execute_chat_completion(provider, model, request)

    assert captured["json"]["messages"] == [
        {"role": "user", "content": "Plan the next support action."}
    ]
    assert result.completion == "Next action planned."


def test_openai_compatible_provider_marks_valid_json_object_as_not_healed(monkeypatch):
    provider = Provider(
        name="external_router",
        adapter_type="openai_compatible",
        status="active",
        health_status="healthy",
        priority=10,
    )
    model = ModelCatalog(
        model_id="router-model",
        provider_id=1,
        provider_model_name="gpt-4.1-mini",
        status="active",
    )
    request = schemas.ChatCompletionRequest(
        model="router-model",
        messages=[schemas.ChatMessage(role="user", content="Return valid JSON")],
        response_format=schemas.ResponseFormat(type="json_object"),
    )

    def fake_post(url, json, headers, timeout):
        return DummyResponse(
            {
                "choices": [
                    {"message": {"content": "{\"ok\":true,\"message\":\"hello\"}"}},
                ],
                "usage": {
                    "prompt_tokens": 8,
                    "completion_tokens": 6,
                },
            }
        )

    monkeypatch.setenv(
        "PROVIDER_EXTERNAL_ROUTER_BASE_URL",
        "https://example.test/v1",
    )
    monkeypatch.setenv("PROVIDER_EXTERNAL_ROUTER_API_KEY", "secret-key")
    monkeypatch.setattr(providers.httpx, "post", fake_post)

    result = providers.execute_chat_completion(provider, model, request)

    assert result.structured_output == {"ok": True, "message": "hello"}
    assert result.response_healed is False
    assert result.healing_strategy is None
