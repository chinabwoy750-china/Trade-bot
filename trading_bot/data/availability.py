"""Data availability map per asset class detailing verified vs unavailable market signals."""

from enum import Enum

from pydantic import BaseModel, Field


class SignalAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    ESTIMATED = "ESTIMATED"


class AssetClassDataAvailability(BaseModel):
    """Specification of verified vs unavailable signals for an asset class and broker."""
    asset_class: str
    broker: str
    real_signals: list[str] = Field(default_factory=list)
    unavailable_signals: list[str] = Field(default_factory=list)
    volume_type: str  # "TICK_VOLUME" | "BAR_VOLUME" | "CENTRAL_TAPE"
    notes: str


# Institutional data-availability ground truth
DATA_AVAILABILITY_MAP: dict[str, AssetClassDataAvailability] = {
    "FOREX": AssetClassDataAvailability(
        asset_class="FOREX",
        broker="OANDA (Practice REST v3)",
        real_signals=[
            "OHLCV_PRICE",
            "TICK_VOLUME",
            "MULTI_TIMEFRAME_TREND",
            "RSI",
            "EMA_STACK",
            "ATR",
            "BOLLINGER_BANDS",
            "PIVOT_POINTS",
            "MACD",
        ],
        unavailable_signals=[
            "ORDER_BOOK_L2_L3_DEPTH",
            "ORDER_BOOK_IMBALANCE",
            "TAKER_BUY_SELL_RATIO",
            "CENTRAL_VOLUME_DELTA",
            "FUTURES_FUNDING_RATE",
            "LIQUIDATIONS",
        ],
        volume_type="TICK_VOLUME",
        notes=(
            "OANDA Forex provides tick volume (number of price quote changes per candle), "
            "NOT centralized volume. In the decentralized retail spot forex market, real order-book depth, "
            "taker buy/sell volume, and futures funding rates DO NOT exist. The decision agent MUST NOT "
            "expect or hallucinate order-book or taker delta for Forex pairs."
        ),
    ),
    "METAL": AssetClassDataAvailability(
        asset_class="METAL",
        broker="OANDA (Practice REST v3)",
        real_signals=[
            "OHLCV_PRICE",
            "TICK_VOLUME",
            "MULTI_TIMEFRAME_TREND",
            "RSI",
            "EMA_STACK",
            "ATR",
            "BOLLINGER_BANDS",
            "PIVOT_POINTS",
        ],
        unavailable_signals=[
            "ORDER_BOOK_L2_L3_DEPTH",
            "ORDER_BOOK_IMBALANCE",
            "TAKER_BUY_SELL_RATIO",
            "CENTRAL_VOLUME_DELTA",
        ],
        volume_type="TICK_VOLUME",
        notes="Gold (XAU/USD) CFD is OTC and uses tick volume. No central exchange order-book or taker tape.",
    ),
    "CRYPTO": AssetClassDataAvailability(
        asset_class="CRYPTO",
        broker="Alpaca (Crypto Data v1beta3 / Paper)",
        real_signals=[
            "OHLCV_PRICE",
            "REAL_BAR_VOLUME",
            "ESTIMATED_VOLUME_DELTA_FROM_CANDLES",
            "RSI",
            "EMA_STACK",
            "ATR",
            "VWAP",
            "BOLLINGER_BANDS",
            "MACD",
        ],
        unavailable_signals=[
            "FULL_ORDER_BOOK_DEPTH",
            "TAKER_BUY_SELL_RATIO",
            "FUTURES_FUNDING_RATE",
            "DERIVATIVE_LIQUIDATIONS",
        ],
        volume_type="BAR_VOLUME",
        notes=(
            "Alpaca crypto feed provides spot bar trade volume and VWAP. "
            "Taker buy/sell flow and derivatives funding rates are NOT available on Alpaca Spot Paper. "
            "The decision agent MUST evaluate spot trends and bar volume, without inventing missing order-book signals."
        ),
    ),
}


def get_data_availability(asset_class: str) -> AssetClassDataAvailability:
    """Retrieve data availability specification for a given asset class."""
    norm = asset_class.upper().strip()
    if norm in DATA_AVAILABILITY_MAP:
        return DATA_AVAILABILITY_MAP[norm]
    # Default to Forex conservative setup
    return DATA_AVAILABILITY_MAP["FOREX"]


def format_data_availability_prompt_block(asset_class: str) -> str:
    """Format structured instruction text to be injected into the LLM decision prompt."""
    spec = get_data_availability(asset_class)
    return (
        f"[DATA AVAILABILITY FOR {spec.asset_class} ON {spec.broker}]\n"
        f"- Real Verified Signals: {', '.join(spec.real_signals)}\n"
        f"- UNAVAILABLE SIGNALS: {', '.join(spec.unavailable_signals)}\n"
        f"- Volume Type: {spec.volume_type}\n"
        f"- CRITICAL INSTRUCTION: {spec.notes}\n"
        f"Do NOT reference or condition your thesis on unavailable signals."
    )
