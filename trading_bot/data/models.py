"""Data layer value objects and indicator result containers."""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class Timeframe(str, Enum):
    """Supported multi-timeframe granularities."""
    M15 = "M15"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"


class PivotPoints(BaseModel):
    """Classical daily pivot levels."""
    pivot: float
    r1: float
    r2: float
    s1: float
    s2: float


class BollingerBandsResult(BaseModel):
    """Bollinger Bands (20, 2.0)."""
    upper: float
    middle: float
    lower: float
    bandwidth: float
    percent_b: float


class MacdResult(BaseModel):
    """MACD (12, 26, 9)."""
    macd: float
    signal: float
    histogram: float


class EmaStack(BaseModel):
    """Multi-period Exponential Moving Averages."""
    ema_9: float
    ema_21: float
    ema_50: float
    ema_200: float | None = None

    @property
    def is_bullish_aligned(self) -> bool:
        """True if 9 > 21 > 50."""
        return self.ema_9 > self.ema_21 > self.ema_50

    @property
    def is_bearish_aligned(self) -> bool:
        """True if 9 < 21 < 50."""
        return self.ema_9 < self.ema_21 < self.ema_50


class IndicatorsResult(BaseModel):
    """Composite calculated technical indicators for a given instrument."""
    symbol: str
    timeframe: Timeframe
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    latest_close: float
    rsi: float
    atr: float
    vwap: float | None = None
    vwap_distance_pct: float | None = None
    ema_stack: EmaStack
    bollinger: BollingerBandsResult
    macd: MacdResult
    pivots: PivotPoints | None = None
    volume_delta: float = 0.0
    volume_spike_ratio: float = 1.0  # Current vol / 20-period avg vol
    is_volume_spike: bool = False
    trend_direction: str = "NEUTRAL"  # BULLISH | BEARISH | NEUTRAL
