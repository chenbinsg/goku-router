"""
Provider execution layer.

Adapters:
  mock              — echo responses for local testing
  openai_compatible — OpenAI-compatible HTTP API (covers OpenAI, Anthropic via proxy,
                      vLLM, Ollama, LM Studio, DeepSeek, Qwen, etc.)

v0.3: Real token counting via tiktoken
v0.4: Circuit breaker integration + live latency EMA updates
"""
from __future__ import annotations
from datetime import datetime
import time
import logging
from dataclasses import dataclass
from typing import Any
import json
import uuid

import httpx

from .. import schemas
from ..config import get_provider_runtime_config
from ..models import ModelCatalog, Provider
from .token_counter import count_messages_tokens, count_tokens
from .circuit_breaker import circuit_breakers

logger = logging.getLogger(__name__)


class ProviderExecutionError(Exception):
    pass


@dataclass
class ProviderResult:
    completion: str
    prompt_tokens: int
    completion_tokens: int
    cost_amount: float
    latency_ms: float = 0.0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    provider_reported_cost: float = 0.0
    tool_calls: list[dict[str, Any]] | None = None
    structured_output: Any = None
    response_healed: bool = False
    healing_strategy: str | None = None


# ── Text extraction helpers ────────────────────────────────────────────────────

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


# ── Structured output repair ───────────────────────────────────────────────────

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
        repaired = {"answer": completion, "provider": provider_name}
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


# ── Mock adapter ───────────────────────────────────────────────────────────────

def _execute_mock_chat_completion(
    provider: Provider,
    model: ModelCatalog,
    request: schemas.ChatCompletionRequest,
    prompt: str,
) -> ProviderResult:
    last_message = _extract_text_content(request.messages[-1].content) if request.messages else ""
    completion = f"[{provider.name}] {model.provider_model_name}: Echo: {last_message}"
    tool_calls = _build_mock_tool_calls(request, prompt)
    completion, structured_output, response_healed, healing_strategy = _parse_or_repair_structured_output(
        request=request, completion=completion, provider_name=provider.name,
    )
    # Real token counting (v0.3)
    messages_dicts = [m.model_dump(exclude_none=True) for m in request.messages]
    prompt_tokens = count_messages_tokens(messages_dicts, model="gpt-4o")
    completion_tokens = count_tokens(completion, model="gpt-4o")
    cost_amount = round(
        (prompt_tokens / 1000) * provider.input_cost_per_1k
        + (completion_tokens / 1000) * provider.output_cost_per_1k,
        6,
    )
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


# ── OpenAI-compatible adapter (covers vLLM, Ollama, OpenAI, DeepSeek, etc.) ───
def _log_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _emit_call_log(record: dict[str, Any]) -> None:
    """Emit one single-line JSON trace record to stdout for log-based analytics.

    Single line on purpose: the k8s log collector ingests one record per line, so a
    multi-line (pretty-printed) payload would be split into many fragmented entries.
    """
    # flush=True is required: in a container, stdout is block-buffered (not line-
    # buffered), so without flushing these lines sit in the buffer and appear late
    # or get lost on crash — while uvicorn's own logs (which flush) show normally.
    print(f"[{_log_timestamp()}] llm_trace {json.dumps(record, ensure_ascii=False, default=str)}", flush=True)
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
    payload: dict[str, Any] = {
        "model": model.provider_model_name,
        "messages": [message.model_dump(exclude_none=True) for message in request.messages],
    }
    for key in ["temperature", "top_p", "max_tokens", "presence_penalty", "stop", "tool_choice"]:
        value = getattr(request, key)
        if value is not None:
            payload[key] = value
    if request.tools is not None:
        payload["tools"] = [tool.model_dump() for tool in request.tools]
    if request.response_format is not None:
        payload["response_format"] = request.response_format.model_dump(exclude_none=True)
    # Pass through vLLM / Qwen3 extra fields (chat_template_kwargs, top_k, etc.)
    if request.extra_body:
        payload.update(request.extra_body)

    # For the openrouter provider (vLLM serving Qwen3 models), always inject
    # thinking-off + recommended sampling params unless the caller already set them.
    if provider.name == "openrouter":
        payload.setdefault("top_k", 20)
        payload.setdefault("top_p", 0.8)
        payload.setdefault("presence_penalty", 1.5)
        ctk = payload.setdefault("chat_template_kwargs", {})
        ctk.setdefault("enable_thinking", False)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Determine timeout: internal providers use shorter timeout; large remote models need more time 
    # external default raised to 300 s — 35B models (Qwen3.6) may take 3–4 min for long outputs
    timeout = 15.0 if getattr(provider, "host_type", "external") == "internal" else 300.0

    taskid = request.task_id or "no_taskid"
    trace_id = str(uuid.uuid4())
    request_bytes = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    num_messages = len(request.messages)

    # Full request payload — DEBUG only (off by default; may contain prompt content).
    # Guarded so json.dumps doesn't run on the hot path when DEBUG is disabled.
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("llm_request task=%s trace=%s payload=%s",
                     taskid, trace_id, json.dumps(payload, ensure_ascii=False))

    started_at = time.perf_counter()
    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:
        # Transport-level failure (timeout, connection refused, DNS, etc.)
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
        _emit_call_log({
            "evt": "llm_call", "ok": False, "task_id": taskid, "trace_id": trace_id,
            "provider": provider.name, "model": model.provider_model_name,
            "error_type": type(exc).__name__, "error": str(exc),
            "latency_ms": elapsed_ms, "req_msgs": num_messages, "req_bytes": request_bytes,
        })
        raise ProviderExecutionError(
            f"Provider {provider.name} request failed: {exc}"
        ) from exc

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
    response_bytes = len(response.content)

    # Full response body — DEBUG only.
    if logger.isEnabledFor(logging.DEBUG):
        try:
            body_debug = json.dumps(response.json(), ensure_ascii=False)
        except Exception:
            body_debug = response.text
        logger.debug("llm_response task=%s trace=%s body=%s", taskid, trace_id, body_debug)

    if not response.is_success:
        # HTTP-level failure (4xx/5xx) — log status, body, size and time spent.
        try:
            body_preview = response.text[:500]
        except Exception:
            body_preview = "<unreadable>"
        _emit_call_log({
            "evt": "llm_call", "ok": False, "task_id": taskid, "trace_id": trace_id,
            "provider": provider.name, "model": model.provider_model_name,
            "status": response.status_code, "error_type": "HTTPStatusError",
            "error": f"HTTP {response.status_code}", "body_preview": body_preview,
            "latency_ms": elapsed_ms, "req_msgs": num_messages,
            "req_bytes": request_bytes, "resp_bytes": response_bytes,
        })
        try:
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

    finish_reason = choices[0].get("finish_reason")
    message = choices[0].get("message") or {}
    completion = _extract_text_content(message.get("content", ""))
    tool_calls = message.get("tool_calls")
    completion, structured_output, response_healed, healing_strategy = _parse_or_repair_structured_output(
        request=request, completion=completion, provider_name=provider.name,
    )
    usage = data.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    # NOTE: `(x or {})` not `x.get(k, {})` — some providers send the *_details key
    # explicitly as null, and dict.get's default only applies when the key is absent.
    cached_tokens = int(
        usage.get("cached_tokens")
        or (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
        or 0
    )
    reasoning_tokens = int(
        usage.get("reasoning_tokens")
        or (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        or 0
    )
    provider_reported_cost = float(usage.get("cost") or data.get("cost") or 0.0)

    # Fallback to tiktoken if provider didn't report usage (v0.3)
    if prompt_tokens == 0 and completion_tokens == 0:
        messages_dicts = [m.model_dump(exclude_none=True) for m in request.messages]
        prompt_tokens = count_messages_tokens(messages_dicts)
        completion_tokens = count_tokens(completion)

    # Single-line analytics record for the successful call.
    _emit_call_log({
        "evt": "llm_call", "ok": True, "task_id": taskid, "trace_id": trace_id,
        "provider": provider.name, "model": model.provider_model_name,
        "status": response.status_code, "finish_reason": finish_reason,
        "latency_ms": elapsed_ms,
        "req_msgs": num_messages, "req_bytes": request_bytes,
        "resp_bytes": response_bytes, "completion_chars": len(completion),
        "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "cached_tokens": cached_tokens, "reasoning_tokens": reasoning_tokens,
        "tool_calls": len(tool_calls) if tool_calls else 0,
        "healed": response_healed,
    })

    return ProviderResult(
        completion=completion,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_amount=0.0,  # computed in crud with provider pricing
        cached_tokens=cached_tokens,
        reasoning_tokens=reasoning_tokens,
        provider_reported_cost=provider_reported_cost,
        tool_calls=tool_calls,
        structured_output=structured_output,
        response_healed=response_healed,
        healing_strategy=healing_strategy,
    )


# ── Public entry point ─────────────────────────────────────────────────────────

def execute_chat_completion(
    provider: Provider,
    model: ModelCatalog,
    request: schemas.ChatCompletionRequest,
) -> ProviderResult:
    """
    Execute a chat completion against the given provider.

    v0.4: Integrates circuit breaker — records success/failure and updates
    provider.avg_latency_ms via EMA after each call.
    """
    if provider.status != "active":
        raise ProviderExecutionError(f"Provider {provider.name} is disabled (status={provider.status})")

    # Circuit breaker check (v0.4)
    if not circuit_breakers.is_available(provider.name):
        raise ProviderExecutionError(
            f"Provider {provider.name} circuit breaker is OPEN — skipping to avoid cascade failures"
        )

    prompt = _extract_prompt(request.messages)

    # Test-only escape hatch for forcing failures in integration tests
    fail_marker = f"[fail:{provider.name}]"
    if fail_marker in prompt:
        circuit_breakers.record_failure(provider.name)
        raise ProviderExecutionError(f"Provider {provider.name} failed for request (test marker)")

    t0 = time.perf_counter()
    try:
        if provider.adapter_type == "mock":
            result = _execute_mock_chat_completion(
                provider=provider, model=model, request=request, prompt=prompt,
            )
        elif provider.adapter_type == "openai_compatible":
            result = _execute_openai_compatible_chat_completion(
                provider=provider, model=model, request=request,
            )
        else:
            raise ProviderExecutionError(f"Unsupported adapter type: {provider.adapter_type}")

        latency_ms = (time.perf_counter() - t0) * 1000
        result.latency_ms = latency_ms

        # Update EMA latency on the provider object (caller commits to DB) (v0.4)
        alpha = getattr(provider, "latency_ema_alpha", None) or 0.1
        previous_latency_ms = getattr(provider, "avg_latency_ms", None) or 0.0
        provider.avg_latency_ms = round(
            alpha * latency_ms + (1 - alpha) * previous_latency_ms, 2
        )

        circuit_breakers.record_success(provider.name)
        return result

    except ProviderExecutionError:
        circuit_breakers.record_failure(provider.name)
        raise
