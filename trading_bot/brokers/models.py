"""Domain models and value objects for broker abstraction."""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class AssetClass(str, Enum):
    FOREX = "FOREX"
    CRYPTO = "CRYPTO"
    METAL = "METAL"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class TimeInForce(str, Enum):
    GTC = "GTC"  # Good Till Cancelled
    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # Fill or Kill
    DAY = "DAY"


class TickerQuote(BaseModel):
    """Latest market quote for an instrument."""
    symbol: str
    bid: float
    ask: float
    last: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @property
    def mid(self) -> float:
        return (self.ask + self.bid) / 2.0


class Candle(BaseModel):
    """OHLCV candlestick data."""
    symbol: str
    timeframe: str  # e.g., "M15", "H1", "H4", "D1"
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    complete: bool = True


class Order(BaseModel):
    """Unified broker order representation."""
    id: str
    client_order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    avg_fill_price: float | None = None
    time_in_force: TimeInForce = TimeInForce.GTC
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Position(BaseModel):
    """Open broker position representation."""
    id: str
    symbol: str
    side: OrderSide
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None
    opened_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AccountState(BaseModel):
    """Unified account balance and equity snapshot."""
    account_id: str
    broker: str
    currency: str = "USD"
    balance: float
    equity: float
    margin_used: float = 0.0
    margin_available: float = 0.0
    unrealized_pnl: float = 0.0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
