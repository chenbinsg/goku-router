"""
Request and response safety pipeline.

Features:
- Blocked word lists (exact match, case-insensitive)
- Regex pattern matching (configurable per workspace)
- Built-in PII pattern detection (email, phone, credit card, SSN, JP My Number)
- Block mode: reject the request/response outright
- Redact mode: replace matched spans with [REDACTED] and continue

Usage:
    from .services.safety import scan_request, scan_response, SafetyViolation
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Built-in PII patterns ──────────────────────────────────────────────────────
_PII_PATTERNS: dict[str, re.Pattern] = {
    "email": re.compile(
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
    ),
    "phone_jp": re.compile(
        r"\b0\d{1,4}[-\s]?\d{1,4}[-\s]?\d{4}\b"
    ),
    "phone_us": re.compile(
        r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
    ),
    "credit_card": re.compile(
        r"\b(?:\d[ \-]?){13,16}\b"
    ),
    "ssn_us": re.compile(
        r"\b\d{3}-\d{2}-\d{4}\b"
    ),
    "my_number_jp": re.compile(
        r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"
    ),
}

# ── Result types ───────────────────────────────────────────────────────────────

@dataclass
class SafetyViolation:
    category: str    # "blocked_word" | "regex_pattern" | "pii_<type>"
    matched: str     # redacted description (never the actual value)
    mode: str        # "block" | "redact"


# ── Internal helpers ───────────────────────────────────────────────────────────

def _check_blocked_words(text: str, words: list[str]) -> SafetyViolation | None:
    text_lower = text.lower()
    for word in words:
        w = word.strip().lower()
        if not w:
            continue
        if w in text_lower:
            return SafetyViolation(category="blocked_word", matched="<blocked>", mode="block")
    return None


def _check_regex_patterns(text: str, patterns: list[str]) -> SafetyViolation | None:
    for pattern_str in patterns:
        p = pattern_str.strip()
        if not p:
            continue
        try:
            if re.search(p, text, re.IGNORECASE):
                return SafetyViolation(
                    category="regex_pattern", matched="<matched>", mode="block"
                )
        except re.error as exc:
            logger.warning("Skipping invalid regex pattern %r: %s", p, exc)
    return None


def _redact_pii(text: str) -> tuple[str, list[SafetyViolation]]:
    """Replace all PII matches with [REDACTED]. Returns (redacted_text, violations)."""
    violations: list[SafetyViolation] = []
    result = text
    offset = 0
    # Collect all matches across all patterns, sorted by position
    all_matches: list[tuple[int, int, str]] = []
    for pii_type, pattern in _PII_PATTERNS.items():
        for m in pattern.finditer(text):
            all_matches.append((m.start(), m.end(), pii_type))
    # Sort by start position, process in order
    all_matches.sort(key=lambda x: x[0])
    for start, end, pii_type in all_matches:
        adj_start = start + offset
        adj_end = end + offset
        replacement = "[REDACTED]"
        result = result[:adj_start] + replacement + result[adj_end:]
        offset += len(replacement) - (end - start)
        violations.append(SafetyViolation(
            category=f"pii_{pii_type}", matched="<pii>", mode="redact"
        ))
    return result, violations


# ── Public API ─────────────────────────────────────────────────────────────────

def scan_request(
    text: str,
    blocked_words: list[str],
    regex_patterns: list[str],
    detect_pii: bool = False,
) -> tuple[bool, SafetyViolation | None]:
    """
    Scan an incoming request prompt.

    Returns:
        (is_safe, violation)
        is_safe=False → caller should reject the request with 451.
    """
    v = _check_blocked_words(text, blocked_words)
    if v:
        return False, v

    v = _check_regex_patterns(text, regex_patterns)
    if v:
        return False, v

    if detect_pii:
        _, pii_violations = _redact_pii(text)
        if pii_violations:
            return False, pii_violations[0]

    return True, None


def scan_response(
    text: str,
    blocked_words: list[str],
    regex_patterns: list[str],
    detect_pii: bool = False,
    redact_pii: bool = True,
) -> tuple[str, bool, SafetyViolation | None]:
    """
    Scan an outgoing provider response.

    Returns:
        (output_text, was_modified, blocking_violation)
        - If a blocked_word/regex hits: text replaced with policy notice, was_modified=True
        - If PII detected and redact_pii=True: PII spans replaced, was_modified=True
        - blocking_violation is set only when the entire response is suppressed
    """
    # Hard block first
    v = _check_blocked_words(text, blocked_words)
    if v:
        return "[RESPONSE BLOCKED: content policy violation]", True, v

    v = _check_regex_patterns(text, regex_patterns)
    if v:
        return "[RESPONSE BLOCKED: content policy violation]", True, v

    # PII redaction (soft — partial replacement, response still returned)
    if detect_pii and redact_pii:
        redacted, violations = _redact_pii(text)
        if violations:
            return redacted, True, None

    return text, False, None
