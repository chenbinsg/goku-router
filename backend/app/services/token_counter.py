"""
Real token counting using tiktoken.
Falls back to word-count approximation if tiktoken is unavailable.
"""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken not installed — falling back to word-count approximation. "
                   "Install with: pip install tiktoken")


def _get_encoder(model: str):
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """Count tokens in a text string."""
    if not text:
        return 0
    if not _TIKTOKEN_AVAILABLE:
        return max(len(text.split()), 1)
    try:
        enc = _get_encoder(model)
        return len(enc.encode(text))
    except Exception:
        return max(len(text.split()), 1)


def count_messages_tokens(messages: list[dict[str, Any]], model: str = "gpt-4o") -> int:
    """
    Count tokens for a list of chat messages including role/overhead tokens.
    Follows OpenAI's token counting formula.
    """
    if not messages:
        return 0
    if not _TIKTOKEN_AVAILABLE:
        total = sum(max(len(str(m.get("content", "")).split()), 1) for m in messages)
        return total + len(messages) * 4  # role overhead estimate
    try:
        enc = _get_encoder(model)
        total = 0
        for message in messages:
            total += 4  # every message: <|start|>role\ncontent<|end|>
            role = message.get("role", "")
            if role:
                total += len(enc.encode(role))
            content = message.get("content", "") or ""
            if isinstance(content, str):
                total += len(enc.encode(content))
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        total += len(enc.encode(str(part.get("text", ""))))
        total += 2  # reply priming tokens
        return total
    except Exception:
        return sum(max(len(str(m.get("content", "")).split()), 1) for m in messages)
