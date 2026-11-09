"""Strict Pydantic schemas for AI decision agent output."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class TradeAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


# Backward-compatible alias
ActionType = TradeAction


class EntryType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class HoldReasonCode(str, Enum):
    NO_EDGE = "NO_EDGE"
    DATA_STALE = "DATA_STALE"
    RISK_LIMIT = "RISK_LIMIT"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    OUTSIDE_SESSION = "OUTSIDE_SESSION"
    INPUT_INTEGRITY_FAILURE = "INPUT_INTEGRITY_FAILURE"
    OTHER = "OTHER"


class TradeDecision(BaseModel):
    """Schema for actionable BUY or SELL trade proposals."""
    action: Literal[TradeAction.BUY, TradeAction.SELL]
    symbol: str = Field(..., min_length=1, description="Instrument symbol (e.g. EUR_USD, BTC/USD)")
    quantity: float = Field(default=1.0, gt=0.0, description="Proposed order size/units")
    entry_type: EntryType = Field(default=EntryType.MARKET, description="MARKET or LIMIT")
    limit_price: float | None = Field(default=None, description="Required if entry_type is LIMIT")
    stop_loss: float = Field(..., gt=0.0, description="Mandatory protective stop price")
    take_profit: float = Field(..., gt=0.0, description="Mandatory profit target price")
    risk_reward: float = Field(default=1.5, ge=0.0, description="R:R ratio, evaluated by risk manager")
    risk_usd: float = Field(default=0.0, ge=0.0, description="Estimated dollar risk amount")
    reasoning: str = Field(..., min_length=5, description="One-sentence thesis justifying trade")
    invalidation_condition: str = Field(default="Market structure invalidation", description="Price or event that proves thesis wrong")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Agent confidence score between 0.0 and 1.0")

    @model_validator(mode="after")
    def validate_levels(self) -> "TradeDecision":
        # Check limit price when entry_type is LIMIT
        if self.entry_type == EntryType.LIMIT and self.limit_price is None:
            raise ValueError("limit_price is required when entry_type is LIMIT")

        effective_entry = self.limit_price if self.limit_price is not None else None

        # If effective_entry is known, validate stop/take-profit orientation
        if effective_entry is not None:
            if self.action == TradeAction.BUY:
                if self.stop_loss >= effective_entry:
                    raise ValueError(f"BUY order stop_loss ({self.stop_loss}) must be below entry ({effective_entry})")
                if self.take_profit <= effective_entry:
                    raise ValueError(f"BUY order take_profit ({self.take_profit}) must be above entry ({effective_entry})")
            elif self.action == TradeAction.SELL:
                if self.stop_loss <= effective_entry:
                    raise ValueError(f"SELL order stop_loss ({self.stop_loss}) must be above entry ({effective_entry})")
                if self.take_profit >= effective_entry:
                    raise ValueError(f"SELL order take_profit ({self.take_profit}) must be below entry ({effective_entry})")

        return self


class HoldDecision(BaseModel):
    """Schema for HOLD decisions when conditions for entry are not met."""
    action: Literal[TradeAction.HOLD] = TradeAction.HOLD
    reason_code: HoldReasonCode = Field(..., description="Standardized hold reason code")
    reasoning: str = Field(..., min_length=3, description="Rationale for holding")
    symbol: str | None = None
    missing_condition_diagnostic: str | None = None


# Discriminated union of valid decision outputs
DecisionResult = TradeDecision | HoldDecision

