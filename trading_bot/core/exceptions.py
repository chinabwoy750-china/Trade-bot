"""Custom typed exceptions for trading bot safety and domain logic."""


class TradingBotException(Exception):
    """Base exception for all trading bot errors."""


class LiveTradingNotAllowedException(TradingBotException):
    """Raised when live trading is initiated without required safety confirmations."""


class RiskVetoException(TradingBotException):
    """Raised when the deterministic risk manager vetoes an order or proposal."""
    def __init__(self, rule_name: str, message: str, details: dict | None = None) -> None:
        super().__init__(f"RISK VETO [{rule_name}]: {message}")
        self.rule_name = rule_name
        self.details = details or {}


class StaleDataException(TradingBotException):
    """Raised when market data exceeds maximum age threshold."""
    def __init__(self, symbol: str, age_seconds: float, max_age_seconds: float) -> None:
        super().__init__(
            f"DATA_STALE for {symbol}: age {age_seconds:.1f}s exceeds threshold {max_age_seconds:.1f}s"
        )
        self.symbol = symbol
        self.age_seconds = age_seconds
        self.max_age_seconds = max_age_seconds


class InputIntegrityException(TradingBotException):
    """Raised when external untrusted text contains prompt injection or malformed data."""
    def __init__(self, source: str, reason: str) -> None:
        super().__init__(f"INPUT_INTEGRITY_FAILURE in {source}: {reason}")
        self.source = source
        self.reason = reason


class InvalidDecisionException(TradingBotException):
    """Raised when decision agent output is invalid or fails Pydantic schema validation."""


class BrokerException(TradingBotException):
    """Raised when a broker API request fails or disconnects."""


class MarketClosedException(TradingBotException):
    """Raised when trying to execute during outside session hours."""


class DailyLossHaltException(RiskVetoException):
    """Raised when daily loss limit is hit and trading must halt for the remainder of day."""


class ConsecutiveLossHaltException(RiskVetoException):
    """Raised when consecutive loss count threshold is reached."""
