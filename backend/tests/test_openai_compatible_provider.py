from app import schemas
from app.models import ModelCatalog, Provider
from app.services import providers


class DummyResponse:
    def __init__(self, payload, status_code=200, text="{}"):
        self._payload = payload
        self.status_code = status_code
        self.is_success = 200 <= status_code < 300
        self.content = b"{}"
        self.text = text

    def raise_for_status(self):
        if not self.is_success:
            import httpx
            raise httpx.HTTPError(f"HTTP {self.status_code}")
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


def test_qwen_defaults_apply_to_backup_provider_name(monkeypatch):
    # A real vLLM Qwen node declares it accepts the chat-template knobs.
    provider = Provider(
        name="TOKYO_QWEN",
        adapter_type="openai_compatible",
        status="active",
        health_status="healthy",
        priority=75,
        supported_parameters="temperature,top_p,max_tokens,stop,tools,tool_choice,response_format,top_k,chat_template_kwargs,presence_penalty",
    )
    model = ModelCatalog(
        model_id="Qwen3.8",
        provider_id=2,
        provider_model_name="Qwen/Qwen3.8-27B-FP8",
        status="active",
    )
    request = schemas.ChatCompletionRequest(
        model="Qwen3.8",
        messages=[schemas.ChatMessage(role="user", content="Reply OK only.")],
    )
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["json"] = json
        return DummyResponse(
            {
                "choices": [{"message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 1},
            }
        )

    monkeypatch.setenv("PROVIDER_TOKYO_QWEN_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("PROVIDER_TOKYO_QWEN_API_KEY", "secret-key")
    monkeypatch.setattr(providers.httpx, "post", fake_post)

    result = providers.execute_chat_completion(provider, model, request)

    assert result.completion == "OK"
    assert captured["json"]["top_k"] == 20
    assert captured["json"]["top_p"] == 0.8
    assert captured["json"]["presence_penalty"] == 1.5
    assert captured["json"]["chat_template_kwargs"] == {"enable_thinking": False}


def test_vllm_extra_body_stripped_for_non_qwen_provider(monkeypatch):
    # Qwen down → fail over to a plain OpenAI provider.  The client's Qwen
    # extra_body must not be forwarded, or OpenAI returns 400 and the whole
    # candidate set is marked unavailable.
    provider = Provider(
        name="openai_backup",
        adapter_type="openai_compatible",
        status="active",
        health_status="healthy",
        priority=10,
    )
    model = ModelCatalog(
        model_id="gpt-4.1-mini",
        provider_id=3,
        provider_model_name="gpt-4.1-mini",
        status="active",
    )
    request = schemas.ChatCompletionRequest(
        model="gpt-4.1-mini",
        messages=[schemas.ChatMessage(role="user", content="Reply OK only.")],
        extra_body={
            "chat_template_kwargs": {"enable_thinking": False},
            "top_k": 20,
            "repetition_penalty": 1.05,
            "user_tag": "keep-me",  # non-vLLM extra must survive
        },
    )
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["json"] = json
        return DummyResponse(
            {
                "choices": [{"message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 1},
            }
        )

    monkeypatch.setenv("PROVIDER_OPENAI_BACKUP_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("PROVIDER_OPENAI_BACKUP_API_KEY", "secret-key")
    monkeypatch.setattr(providers.httpx, "post", fake_post)

    result = providers.execute_chat_completion(provider, model, request)

    assert result.completion == "OK"
    assert "chat_template_kwargs" not in captured["json"]
    assert "top_k" not in captured["json"]
    assert "repetition_penalty" not in captured["json"]
    assert captured["json"]["user_tag"] == "keep-me"


def test_vllm_extra_body_preserved_for_qwen_provider(monkeypatch):
    # A genuine Qwen upstream declares support for the knobs, so they pass through.
    provider = Provider(
        name="TOKYO_QWEN",
        adapter_type="openai_compatible",
        status="active",
        health_status="healthy",
        priority=75,
        supported_parameters="temperature,top_p,max_tokens,stop,tools,tool_choice,response_format,top_k,chat_template_kwargs",
    )
    model = ModelCatalog(
        model_id="Qwen3.8",
        provider_id=2,
        provider_model_name="Qwen/Qwen3.8-27B-FP8",
        status="active",
    )
    request = schemas.ChatCompletionRequest(
        model="Qwen3.8",
        messages=[schemas.ChatMessage(role="user", content="Reply OK only.")],
        extra_body={"top_k": 40, "chat_template_kwargs": {"enable_thinking": True}},
    )
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["json"] = json
        return DummyResponse(
            {
                "choices": [{"message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 1},
            }
        )

    monkeypatch.setenv("PROVIDER_TOKYO_QWEN_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("PROVIDER_TOKYO_QWEN_API_KEY", "secret-key")
    monkeypatch.setattr(providers.httpx, "post", fake_post)

    result = providers.execute_chat_completion(provider, model, request)

    assert result.completion == "OK"
    # Client-supplied values win over the setdefault Qwen defaults.
    assert captured["json"]["top_k"] == 40
    assert captured["json"]["chat_template_kwargs"] == {"enable_thinking": True}


def test_qwen_model_on_strict_gateway_omits_unsupported_knobs(monkeypatch):
    # Production incident: Qwen3.8 proxied by an OpenRouter-style gateway whose
    # supported_parameters lacks top_k/chat_template_kwargs.  Sending them 400'd
    # and cascaded into "all providers unavailable".  The knobs (from both the
    # Qwen defaults block and the client's extra_body) must be dropped, leaving a
    # clean payload the gateway accepts.
    provider = Provider(
        name="TOKENSTARS_OPENROUTER",
        adapter_type="openai_compatible",
        status="active",
        health_status="healthy",
        priority=1,
        supported_parameters="temperature,top_p,max_tokens,stop,tools,tool_choice,response_format",
    )
    model = ModelCatalog(
        model_id="Qwen3.8",
        provider_id=13,
        provider_model_name="qwen/qwen3.8",
        status="active",
    )
    request = schemas.ChatCompletionRequest(
        model="Qwen3.8",
        messages=[schemas.ChatMessage(role="user", content="Reply OK only.")],
        extra_body={"chat_template_kwargs": {"enable_thinking": False}, "top_k": 20},
    )
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["json"] = json
        return DummyResponse(
            {
                "choices": [{"message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 1},
            }
        )

    monkeypatch.setenv("PROVIDER_TOKENSTARS_OPENROUTER_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("PROVIDER_TOKENSTARS_OPENROUTER_API_KEY", "secret-key")
    monkeypatch.setattr(providers.httpx, "post", fake_post)

    result = providers.execute_chat_completion(provider, model, request)

    assert result.completion == "OK"
    # None of the Qwen-only knobs may reach a gateway that does not support them.
    for unsupported in ("top_k", "chat_template_kwargs", "presence_penalty"):
        assert unsupported not in captured["json"]
    # Supported params still go through.
    assert captured["json"]["top_p"] == 0.8  # injected Qwen default, and supported


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
    monkeypatch.setenv("OPENROUTER_FOLD_SYSTEM", "true")
    monkeypatch.setattr(providers.httpx, "post", fake_post)

    result = providers.execute_chat_completion(provider, model, request)

    assert captured["json"]["messages"] == [
        {"role": "user", "content": "Plan the next support action."}
    ]
    assert result.completion == "Next action planned."


def test_openrouter_provider_merges_system_prompt_into_first_user(monkeypatch):
    provider = Provider(
        name="openrouter",
        adapter_type="openai_compatible",
        status="active",
        health_status="healthy",
        priority=10,
    )
    model = ModelCatalog(
        model_id="Qwen3.6",
        provider_id=1,
        provider_model_name="Qwen3.6-35B-A3B-FP8",
        status="active",
    )
    request = schemas.ChatCompletionRequest(
        model="Qwen3.6",
        messages=[
            schemas.ChatMessage(role="system", content="Follow policy."),
            schemas.ChatMessage(role="user", content="Reply OK only."),
        ],
    )

    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["json"] = json
        return DummyResponse(
            {
                "choices": [
                    {"message": {"content": "OK"}},
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 1,
                },
            }
        )

    monkeypatch.setenv("PROVIDER_OPENROUTER_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("PROVIDER_OPENROUTER_API_KEY", "secret-key")
    monkeypatch.setenv("OPENROUTER_FOLD_SYSTEM", "true")
    monkeypatch.setattr(providers.httpx, "post", fake_post)

    result = providers.execute_chat_completion(provider, model, request)

    assert captured["json"]["messages"] == [
        {"role": "user", "content": "Follow policy.\n\nReply OK only."}
    ]


def test_openrouter_provider_preserves_system_role_by_default(monkeypatch):
    """New default: system role is preserved (NOT folded into user)."""
    provider = Provider(name="openrouter", adapter_type="openai_compatible",
                        status="active", health_status="healthy", priority=10)
    model = ModelCatalog(model_id="qwen3.6", provider_id=1,
                         provider_model_name="Qwen3.6-35B-A3B-FP8", status="active")
    request = schemas.ChatCompletionRequest(
        model="qwen3.6",
        messages=[
            schemas.ChatMessage(role="system", content="Follow policy."),
            schemas.ChatMessage(role="user", content="Reply OK only."),
        ],
    )
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["json"] = json
        return DummyResponse({"choices": [{"message": {"content": "OK"}}],
                              "usage": {"prompt_tokens": 5, "completion_tokens": 1}})

    monkeypatch.delenv("OPENROUTER_FOLD_SYSTEM", raising=False)
    monkeypatch.setenv("PROVIDER_OPENROUTER_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("PROVIDER_OPENROUTER_API_KEY", "secret-key")
    monkeypatch.setattr(providers.httpx, "post", fake_post)

    providers.execute_chat_completion(provider, model, request)

    assert captured["json"]["messages"] == [
        {"role": "system", "content": "Follow policy."},
        {"role": "user", "content": "Reply OK only."},
    ]


def test_openrouter_provider_auto_degrades_on_system_rejection(monkeypatch):
    """If the backend rejects the system role, fold system into user and retry once."""
    provider = Provider(name="openrouter", adapter_type="openai_compatible",
                        status="active", health_status="healthy", priority=10)
    model = ModelCatalog(model_id="qwen3.6", provider_id=1,
                         provider_model_name="Qwen3.6-35B-A3B-FP8", status="active")
    request = schemas.ChatCompletionRequest(
        model="qwen3.6",
        messages=[
            schemas.ChatMessage(role="system", content="Follow policy."),
            schemas.ChatMessage(role="user", content="Reply OK only."),
        ],
    )
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append(json["messages"])
        if len(calls) == 1:
            return DummyResponse({}, status_code=400,
                                 text="System role is not supported by this model's chat template")
        return DummyResponse({"choices": [{"message": {"content": "OK"}}],
                              "usage": {"prompt_tokens": 5, "completion_tokens": 1}})

    monkeypatch.delenv("OPENROUTER_FOLD_SYSTEM", raising=False)
    monkeypatch.setenv("PROVIDER_OPENROUTER_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("PROVIDER_OPENROUTER_API_KEY", "secret-key")
    monkeypatch.setattr(providers.httpx, "post", fake_post)

    result = providers.execute_chat_completion(provider, model, request)

    assert len(calls) == 2  # first (with system) failed, retried once
    # first attempt kept the system role; the retry folded it into the user turn
    assert calls[0][0]["role"] == "system"
    assert calls[1] == [{"role": "user", "content": "Follow policy.\n\nReply OK only."}]
    assert result.completion == "OK"
    assert result.completion == "OK"


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
