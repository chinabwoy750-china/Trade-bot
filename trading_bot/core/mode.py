"""Mode safety gate: strictly prevents live trading unless explicitly confirmed."""

import os
from enum import Enum

from trading_bot.core.exceptions import LiveTradingNotAllowedException


class TradingMode(str, Enum):
    """Supported operational modes for the trading system."""
    DEMO = "demo"
    BACKTEST = "backtest"
    LIVE = "live"

    @classmethod
    def from_string(cls, value: str) -> "TradingMode":
        """Convert string to TradingMode enum with case-insensitive matching."""
        val = value.strip().lower()
        for mode in cls:
            if mode.value == val:
                return mode
        raise ValueError(
            f"Invalid mode '{value}'. Allowed modes are: {[m.value for m in cls]}"
        )


class ModeGate:
    """Hard safety barrier enforcing demo/paper trading safety.
    
    Live trading is physically blocked unless:
    1. MODE is explicitly set to 'live'
    2. LIVE_CONFIRM is explicitly set to 'I_UNDERSTAND_THE_RISK'
    """
    
    REQUIRED_LIVE_CONFIRMATION = "I_UNDERSTAND_THE_RISK"

    @classmethod
    def get_mode(cls) -> TradingMode:
        """Resolve current trading mode from environment variables."""
        raw_mode = os.getenv("MODE", "demo").strip().lower()
        if not raw_mode:
            raw_mode = "demo"
        return TradingMode.from_string(raw_mode)

    @classmethod
    def validate_safety(cls) -> TradingMode:
        """Verify safety constraints for the active mode.
        
        Raises:
            LiveTradingNotAllowedException: if LIVE mode is attempted without exact confirmation.
        """
        mode = cls.get_mode()
        if mode == TradingMode.LIVE:
            confirmation = os.getenv("LIVE_CONFIRM", "").strip()
            if confirmation != cls.REQUIRED_LIVE_CONFIRMATION:
                raise LiveTradingNotAllowedException(
                    "CRITICAL SAFETY LOCK: Live trading requested but confirmation missing or invalid. "
                    f"To enable live trading, you must explicitly set LIVE_CONFIRM='{cls.REQUIRED_LIVE_CONFIRMATION}'. "
                    "Current execution halted."
                )
        return mode

    @classmethod
    def is_live(cls) -> bool:
        """Check if validated live mode is active."""
        try:
            return cls.validate_safety() == TradingMode.LIVE
        except LiveTradingNotAllowedException:
            return False

    @classmethod
    def is_paper_or_backtest(cls) -> bool:
        """Return True if safe mode (demo or backtest) is active."""
        mode = cls.get_mode()
        return mode in (TradingMode.DEMO, TradingMode.BACKTEST)
