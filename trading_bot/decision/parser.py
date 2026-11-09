"""Decision output parser, prompt injection defense, and consecutive hold tracker."""

import json
import re
from typing import Any

from trading_bot.core.exceptions import (
    InputIntegrityException,
    InvalidDecisionException,
)
from trading_bot.core.logger import get_logger
from trading_bot.decision.models import (
    DecisionResult,
    HoldDecision,
    HoldReasonCode,
    TradeAction,
    TradeDecision,
)

logger = get_logger("decision.parser")

# Heuristic patterns indicating prompt injection or jailbreak attempts in external untrusted text
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s*prompt", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?rules", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(an\s+unrestricted|in\s+developer\s+mode|dan)", re.IGNORECASE),
    re.compile(r"execute\s+order\s+override", re.IGNORECASE),
    re.compile(r"bypass\s+risk\s+manager", re.IGNORECASE),
    re.compile(r"place\s+order\s+immediately", re.IGNORECASE),
    re.compile(r"sudo\s+", re.IGNORECASE),
    re.compile(r"<\s*script", re.IGNORECASE),
]


def detect_prompt_injection(text: str) -> bool:
    """Return True if external text exhibits signs of prompt injection or directive hijacking."""
    return any(pattern.search(text) for pattern in PROMPT_INJECTION_PATTERNS)


def sanitize_untrusted_text(
    text: str,
    source: str = "external_text",
    raise_on_injection: bool = True,
) -> str | None:
    """Sanitize and validate untrusted external strings (news, calendar, comments).
    
    If raise_on_injection is False, logs INPUT_INTEGRITY_FAILURE and returns None,
    allowing the offending item to be quarantined while the trading cycle continues.
    """
    if not text:
        return ""

    if detect_prompt_injection(text):
        logger.warning(
            "INPUT_INTEGRITY_FAILURE detected in untrusted text from %s. Content quarantined: %.80s...",
            source,
            text,
        )
        if raise_on_injection:
            raise InputIntegrityException(
                source=source,
                reason="Prompt injection pattern matched in external untrusted input",
            )
        return None

    # Strip dangerous control characters and trim
    clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return clean.strip()


def quarantine_untrusted_items(
    items: list[Any],
    text_extractor: Any,
    source: str = "news_feed",
) -> tuple[list[Any], list[dict[str, Any]]]:
    """Inspect and quarantine only the offending items from an external feed.
    
    Logs INPUT_INTEGRITY_FAILURE for each quarantined item without aborting the cycle.
    Returns:
        (clean_items, quarantined_metadata)
    """
    clean_items: list[Any] = []
    quarantined: list[dict[str, Any]] = []

    for item in items:
        raw_text = text_extractor(item) if callable(text_extractor) else str(item)
        sanitized = sanitize_untrusted_text(raw_text, source=source, raise_on_injection=False)
        if sanitized is None:
            quarantined.append({
                "source": source,
                "flag": "INPUT_INTEGRITY_FAILURE",
                "preview": raw_text[:120],
                "item": item,
            })
        else:
            clean_items.append(item)

    return clean_items, quarantined


def extract_json_block(raw_text: str) -> str:
    """Extract JSON content enclosed in markdown code fences or raw braces."""
    text = raw_text.strip()
    # Match ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    # Match outermost { ... }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace : last_brace + 1].strip()
    return text


def parse_and_validate_decision(raw_output: str) -> DecisionResult:
    """Parse raw LLM string into validated TradeDecision or HoldDecision.
    
    Raises:
        InvalidDecisionException: If parsing or schema validation fails.
    """
    cleaned_json = extract_json_block(raw_output)
    try:
        data = json.loads(cleaned_json)
    except json.JSONDecodeError as err:
        raise InvalidDecisionException(f"Malformed JSON from LLM: {err}") from err

    if not isinstance(data, dict):
        raise InvalidDecisionException(f"Expected JSON object, got {type(data).__name__}")

    raw_action = str(data.get("action", "")).upper()

    try:
        if raw_action in (TradeAction.BUY.value, TradeAction.SELL.value):
            data["action"] = TradeAction(raw_action)
            return TradeDecision.model_validate(data)
        elif raw_action == TradeAction.HOLD.value:
            # Normalize reason_code
            rc = data.get("reason_code", HoldReasonCode.NO_EDGE.value)
            try:
                data["reason_code"] = HoldReasonCode(str(rc).upper())
            except ValueError:
                data["reason_code"] = HoldReasonCode.OTHER
            return HoldDecision.model_validate(data)
        else:
            raise InvalidDecisionException(
                f"Invalid action '{raw_action}'. Must be BUY, SELL, or HOLD."
            )
    except Exception as err:
        raise InvalidDecisionException(f"Schema validation error: {err}") from err


class ConsecutiveHoldTracker:
    """Tracks sequential HOLD decisions and injects diagnostic rationale after N holds."""

    def __init__(self, threshold: int = 4) -> None:
        self.threshold = threshold
        self.consecutive_count: int = 0
        self.last_reasons: list[str] = []

    def record_decision(self, decision: DecisionResult) -> DecisionResult:
        if isinstance(decision, HoldDecision):
            self.consecutive_count += 1
            self.last_reasons.append(decision.reasoning)
            if len(self.last_reasons) > self.threshold:
                self.last_reasons.pop(0)

            if self.consecutive_count >= self.threshold:
                diagnostic = (
                    f"DIAGNOSTIC after {self.consecutive_count} consecutive HOLDs: "
                    f"Market setup missing leading momentum or R:R criteria. "
                    f"Last {len(self.last_reasons)} hold rationales: {'; '.join(self.last_reasons[-3:])}"
                )
                decision.missing_condition_diagnostic = diagnostic
                decision.reasoning = f"{decision.reasoning} [{diagnostic}]"
        else:
            self.consecutive_count = 0
            self.last_reasons.clear()

        return decision

    def reset(self) -> None:
        self.consecutive_count = 0
        self.last_reasons.clear()
