# Goku-Router v1.5.4 Release Notes

## Highlights

- Added single-line structured JSON `llm_trace` records for OpenAI-compatible provider calls.
- Added task ID, trace ID, provider, model, latency, request/response sizes, token usage, tool-call count, and healing metadata to LLM request logs.
- Moved full request/response payload logging behind DEBUG level to reduce noisy production logs.
- Fixed token-detail parsing for providers that return `prompt_tokens_details` or `completion_tokens_details` as `null`.

## Changed

- `backend/app/services/providers.py`

## Validation

- Release contains logging/observability changes only; GitHub Actions will build and publish from this tag.
