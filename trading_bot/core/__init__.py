"""Core module: mode safety gate, exceptions, logging, and time helpers."""

from trading_bot.core.exceptions import (
    BrokerException,
    InputIntegrityException,
    InvalidDecisionException,
    LiveTradingNotAllowedException,
    MarketClosedException,
    RiskVetoException,
    StaleDataException,
    TradingBotException,
)
from trading_bot.core.logger import get_logger, setup_logging
from trading_bot.core.mode import ModeGate, TradingMode
from trading_bot.core.time_utils import is_forex_market_open, utc_now

__all__ = [
    "BrokerException",
    "InputIntegrityException",
    "InvalidDecisionException",
    "LiveTradingNotAllowedException",
    "MarketClosedException",
    "ModeGate",
    "RiskVetoException",
    "StaleDataException",
    "TradingBotException",
    "TradingMode",
    "get_logger",
    "is_forex_market_open",
    "setup_logging",
    "utc_now",
]
