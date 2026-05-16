from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

import httpx

from .. import schemas
from ..config import get_provider_runtime_config
from ..models import ModelCatalog, Provider


class ProviderExecutionError(Exception):
    pass


@dataclass
class ProviderResult:
    completion: str
    prompt_tokens: int
    completion_tokens: int
    cost_amount: float
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    provider_reported_cost: float = 0.0
    tool_calls: list[dict[str, Any]] | None = None
    structured_output: Any = None
    response_healed: bool = False
    healing_strategy: str | None = None


def _extract_prompt(messages: list[schemas.ChatMessage]) -> str:
    return "\n".join(_extract_text_content(message.content) for message in messages)


def _extract_text_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(part for part in parts if part)
    return str(content)


def _generate_schema_value(schema: dict[str, Any], seed_text: str, provider_name: str) -> Any:
    schema_type = schema.get("type", "object")
    if schema_type == "string":
        return f"{provider_name}: {seed_text[:80]}".strip()
    if schema_type == "integer":
        return max(len(seed_text.split()), 1)
    if schema_type == "number":
        return float(max(len(seed_text.split()), 1))
    if schema_type == "boolean":
        return True
    if schema_type == "array":
        item_schema = schema.get("items", {"type": "string"})
        return [_generate_schema_value(item_schema, seed_text, provider_name)]
    if schema_type == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", list(properties.keys()))
        value: dict[str, Any] = {}
        for key in required:
            property_schema = properties.get(key, {"type": "string"})
            value[key] = _generate_schema_value(property_schema, seed_text, provider_name)
        for key, property_schema in properties.items():
            if key not in value:
                value[key] = _generate_schema_value(property_schema, seed_text, provider_name)
        return value
    return seed_text


def _validate_schema(value: Any, schema: dict[str, Any]) -> bool:
    schema_type = schema.get("type", "object")
    if schema_type == "object":
        if not isinstance(value, dict):
            return False
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                return False
        for key, property_value in value.items():
            if key in properties and not _validate_schema(property_value, properties[key]):
                return False
        return True
    if schema_type == "array":
        if not isinstance(value, list):
            return False
        item_schema = schema.get("items", {"type": "string"})
        return all(_validate_schema(item, item_schema) for item in value)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if schema_type == "boolean":
        return isinstance(value, bool)
    return True


def _parse_or_repair_structured_output(
    request: schemas.ChatCompletionRequest,
    completion: str,
    provider_name: str,
) -> tuple[str, Any, bool, str | None]:
    if request.response_format is None:
        return completion, None, False, None

    if request.response_format.type == "json_object":
        try:
            parsed = json.loads(completion)
            if isinstance(parsed, dict):
                return json.dumps(parsed, ensure_ascii=False), parsed, False, None
        except json.JSONDecodeError:
            pass
        repaired = {
            "answer": completion,
            "provider": provider_name,
        }
        return json.dumps(repaired, ensure_ascii=False), repaired, True, "json_object_wrap"

    if request.response_format.type == "json_schema":
        raw_schema = request.response_format.json_schema or {}
        schema = raw_schema.get("schema", raw_schema)
        try:
            parsed = json.loads(completion)
        except json.JSONDecodeError:
            parsed = None
        if parsed is not None and _validate_schema(parsed, schema):
            return json.dumps(parsed, ensure_ascii=False), parsed, False, None
        repaired = _generate_schema_value(schema, completion, provider_name)
        return json.dumps(repaired, ensure_ascii=False), repaired, True, "json_schema_repair"

    return completion, None, False, None


def _build_mock_tool_calls(
    request: schemas.ChatCompletionRequest,
    prompt: str,
) -> list[dict[str, Any]] | None:
    if not request.tools:
        return None
    selected_tool = request.tools[0].function
    return [
        {
            "id": "call_mock_1",
            "type": "function",
            "function": {
                "name": selected_tool.get("name", "tool"),
                "arguments": json.dumps({"input": prompt}, ensure_ascii=False),
            },
        }
    ]


def _execute_mock_chat_completion(
    provider: Provider,
    model: ModelCatalog,
    request: schemas.ChatCompletionRequest,
    prompt: str,
) -> ProviderResult:
    last_message = _extract_text_content(request.messages[-1].content) if request.messages else ""
    completion = (
        f"[{provider.name}] {model.provider_model_name}: "
        f"Echo: {last_message}"
    )
    tool_calls = _build_mock_tool_calls(request, prompt)
    completion, structured_output, response_healed, healing_strategy = _parse_or_repair_structured_output(
        request=request,
        completion=completion,
        provider_name=provider.name,
    )
    prompt_tokens = max(len(prompt.split()), 1)
    completion_tokens = max(len(completion.split()), 1)
    cost_amount = round((prompt_tokens + completion_tokens) * 0.00001, 6)
    return ProviderResult(
        completion=completion,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_amount=cost_amount,
        cached_tokens=0,
        reasoning_tokens=0,
        provider_reported_cost=cost_amount,
        tool_calls=tool_calls,
        structured_output=structured_output,
        response_healed=response_healed,
        healing_strategy=healing_strategy,
    )


def _execute_openai_compatible_chat_completion(
    provider: Provider,
    model: ModelCatalog,
    request: schemas.ChatCompletionRequest,
) -> ProviderResult:
    runtime_config = get_provider_runtime_config(provider.name)
    base_url = runtime_config["base_url"]
    api_key = runtime_config["api_key"]
    if not base_url or not api_key:
        raise ProviderExecutionError(
            f"Provider {provider.name} is missing BASE_URL or API_KEY configuration"
        )

    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model.provider_model_name,
        "messages": [message.model_dump(exclude_none=True) for message in request.messages],
    }
    for key in ["temperature", "top_p", "max_tokens", "stop", "tool_choice"]:
        value = getattr(request, key)
        if value is not None:
            payload[key] = value
    if request.tools is not None:
        payload["tools"] = [tool.model_dump() for tool in request.tools]
    if request.response_format is not None:
        payload["response_format"] = request.response_format.model_dump(exclude_none=True)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ProviderExecutionError(
            f"Provider {provider.name} request failed: {exc}"
        ) from exc

    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise ProviderExecutionError(
            f"Provider {provider.name} returned no completion choices"
        )

    message = choices[0].get("message") or {}
    completion = _extract_text_content(message.get("content", ""))
    tool_calls = message.get("tool_calls")
    completion, structured_output, response_healed, healing_strategy = _parse_or_repair_structured_output(
        request=request,
        completion=completion,
        provider_name=provider.name,
    )
    usage = data.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    cached_tokens = int(
        usage.get("cached_tokens")
        or usage.get("prompt_tokens_details", {}).get("cached_tokens")
        or 0
    )
    reasoning_tokens = int(
        usage.get("reasoning_tokens")
        or usage.get("completion_tokens_details", {}).get("reasoning_tokens")
        or 0
    )
    provider_reported_cost = float(
        usage.get("cost")
        or data.get("cost")
        or 0.0
    )
    if prompt_tokens == 0 and completion_tokens == 0:
        prompt_tokens = max(len(_extract_prompt(request.messages).split()), 1)
        completion_tokens = max(len(completion.split()), 1)

    return ProviderResult(
        completion=completion,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_amount=0.0,
        cached_tokens=cached_tokens,
        reasoning_tokens=reasoning_tokens,
        provider_reported_cost=provider_reported_cost,
        tool_calls=tool_calls,
        structured_output=structured_output,
        response_healed=response_healed,
        healing_strategy=healing_strategy,
    )


def execute_chat_completion(
    provider: Provider,
    model: ModelCatalog,
    request: schemas.ChatCompletionRequest,
) -> ProviderResult:
    if provider.status != "active" or provider.health_status != "healthy":
        raise ProviderExecutionError(f"Provider {provider.name} is unavailable")

    prompt = _extract_prompt(request.messages)
    fail_marker = f"[fail:{provider.name}]"
    if fail_marker in prompt:
        raise ProviderExecutionError(f"Provider {provider.name} failed for request")

    if provider.adapter_type == "mock":
        return _execute_mock_chat_completion(
            provider=provider,
            model=model,
            request=request,
            prompt=prompt,
        )

    if provider.adapter_type == "openai_compatible":
        return _execute_openai_compatible_chat_completion(
            provider=provider,
            model=model,
            request=request,
        )

    raise ProviderExecutionError(f"Unsupported adapter type: {provider.adapter_type}")
