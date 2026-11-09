"""Thread-safe multi-timeframe candle cache (M15, H1, H4, D1) for all configured instruments."""

from collections.abc import Sequence
from datetime import datetime
from threading import RLock

from trading_bot.brokers.models import Candle
from trading_bot.data.indicators import compute_all_indicators
from trading_bot.data.models import IndicatorsResult, Timeframe
from trading_bot.data.staleness import StalenessGuard


class MultiTimeframeCandleStore:
    """Manages cached historical bars across M15, H1, H4, and D1 timeframes.
    
    Provides thread-safe appending, chronological sorting, deduplication,
    buffer truncation, and instant indicator generation.
    """

    def __init__(
        self,
        max_candles_per_timeframe: int = 500,
        staleness_threshold_seconds: float = 300.0,
    ) -> None:
        self.max_candles = max_candles_per_timeframe
        self.staleness_guard = StalenessGuard(max_age_seconds=staleness_threshold_seconds)
        self._lock = RLock()
        # Storage format: {symbol: {timeframe: list[Candle]}}
        self._store: dict[str, dict[str, list[Candle]]] = {}

    def add_candles(self, symbol: str, timeframe: str | Timeframe, candles: Sequence[Candle]) -> int:
        """Insert or merge a sequence of candles, deduplicating by timestamp.
        
        Returns:
            Total count of cached candles for the specified symbol and timeframe.
        """
        tf_str = timeframe.value if isinstance(timeframe, Timeframe) else str(timeframe)

        with self._lock:
            if symbol not in self._store:
                self._store[symbol] = {}
            if tf_str not in self._store[symbol]:
                self._store[symbol][tf_str] = []

            existing = {c.timestamp: c for c in self._store[symbol][tf_str]}
            for c in candles:
                existing[c.timestamp] = c

            # Sort chronologically by timestamp
            sorted_candles = sorted(existing.values(), key=lambda c: c.timestamp)

            # Cap buffer
            if len(sorted_candles) > self.max_candles:
                sorted_candles = sorted_candles[-self.max_candles :]

            self._store[symbol][tf_str] = sorted_candles
            return len(sorted_candles)

    def get_candles(self, symbol: str, timeframe: str | Timeframe, limit: int | None = None) -> list[Candle]:
        """Fetch cached candles chronologically."""
        tf_str = timeframe.value if isinstance(timeframe, Timeframe) else str(timeframe)
        with self._lock:
            candles = self._store.get(symbol, {}).get(tf_str, [])
            if limit is not None and limit > 0:
                return candles[-limit:]
            return list(candles)

    def get_latest_candle(self, symbol: str, timeframe: str | Timeframe = Timeframe.M15) -> Candle | None:
        """Return the most recent candle for symbol and timeframe."""
        tf_str = timeframe.value if isinstance(timeframe, Timeframe) else str(timeframe)
        with self._lock:
            candles = self._store.get(symbol, {}).get(tf_str, [])
            return candles[-1] if candles else None

    def is_symbol_stale(
        self,
        symbol: str,
        timeframe: str | Timeframe = Timeframe.M15,
        now_dt: datetime | None = None,
    ) -> tuple[bool, float]:
        """Check if latest candle for symbol is older than max_age_seconds."""
        latest = self.get_latest_candle(symbol, timeframe)
        if latest is None:
            return True, float("inf")
        return self.staleness_guard.is_candle_stale(latest, now_dt=now_dt)

    def compute_indicators(
        self,
        symbol: str,
        timeframe: Timeframe = Timeframe.M15,
    ) -> IndicatorsResult | None:
        """Compute technical indicator suite from cached candles."""
        candles = self.get_candles(symbol, timeframe)
        if not candles:
            return None

        # Look up daily candle for pivot calculation if available
        d1_candle = self.get_latest_candle(symbol, Timeframe.D1)
        return compute_all_indicators(
            symbol=symbol,
            candles=candles,
            timeframe=timeframe,
            daily_candle=d1_candle,
        )

    def clear(self, symbol: str | None = None) -> None:
        """Clear cache for a specific symbol or all symbols."""
        with self._lock:
            if symbol:
                self._store.pop(symbol, None)
            else:
                self._store.clear()
