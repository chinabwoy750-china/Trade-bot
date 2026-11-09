"""Common broker interface abstraction for OANDA, Alpaca, and Backtest brokers."""

from abc import ABC, abstractmethod

from trading_bot.brokers.models import (
    AccountState,
    Candle,
    Order,
    Position,
    TickerQuote,
)


class BrokerInterface(ABC):
    """Abstract base class for all exchange/broker integrations.
    
    Ensures strict decoupled architecture: whether trading with OANDA,
    Alpaca, or simulated backtester, the execution engine and risk manager
    interact through this uniform contract.
    """

    @property
    @abstractmethod
    def broker_name(self) -> str:
        """Name identifier of the broker implementation."""

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection and verify credentials."""

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check active connection health."""

    @abstractmethod
    async def get_account(self) -> AccountState:
        """Fetch current balance, equity, and margin information."""

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Fetch all currently open positions."""

    @abstractmethod
    async def get_position(self, symbol: str) -> Position | None:
        """Fetch position for a specific symbol if open."""

    @abstractmethod
    async def get_orders(self) -> list[Order]:
        """Fetch all active pending orders."""

    @abstractmethod
    async def place_order(self, order: Order) -> Order:
        """Submit a new order with attached stop loss and take profit.
        
        Args:
            order: Order specification.
            
        Returns:
            Order with updated broker ID and status.
        """

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order by ID."""

    @abstractmethod
    async def modify_position_protection(
        self,
        symbol: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> Position:
        """Update stop loss or take profit for an existing open position."""

    @abstractmethod
    async def close_position(self, symbol: str) -> Order:
        """Close an open position completely at market."""

    @abstractmethod
    async def get_quote(self, symbol: str) -> TickerQuote:
        """Retrieve latest bid/ask market quote."""

    @abstractmethod
    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 100,
    ) -> list[Candle]:
        """Fetch historical OHLCV candles."""
