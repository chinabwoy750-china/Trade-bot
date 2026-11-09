"""Market data staleness detection and timeframe-aware candle freshness enforcement."""

from datetime import datetime, timedelta, timezone

from trading_bot.brokers.models import Candle, TickerQuote
from trading_bot.core.exceptions import StaleDataException
from trading_bot.core.logger import get_logger

logger = get_logger("data.staleness")


class StalenessGuard:
    """Enforces maximum allowable age for quotes and expected closed candles per timeframe.
    
    INVARIANTS:
    1. Real-time quotes: Evaluated against max_age_seconds (default 300s).
    2. Candlestick series: Judged by 'last CLOSED candle must be the expected latest one
       for that timeframe' (M15, H1, H4, D1), NOT a flat 300s on the candle open timestamp.
    """

    def __init__(self, max_quote_age_seconds: float = 300.0, max_age_seconds: float | None = None) -> None:
        self.max_quote_age_seconds = max_age_seconds if max_age_seconds is not None else max_quote_age_seconds
        self.max_age_seconds = self.max_quote_age_seconds

    @staticmethod
    def get_expected_last_closed_candle_time(
        timeframe: str,
        now_dt: datetime | None = None,
    ) -> datetime:
        """Calculate the expected open timestamp of the most recently CLOSED candle.
        
        Assumes candle timestamp marks the open of the interval.
        - M15: interval 15m. Last closed candle opened at prior 15m boundary.
        - H1:  interval 1h.  Last closed candle opened at prior top of hour.
        - H4:  interval 4h.  Aligned to 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC.
        - D1:  interval 24h. Last closed candle opened at 00:00 UTC of previous day.
        """
        now = now_dt or datetime.now(timezone.utc)
        now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)

        tf = timeframe.upper().strip()

        if tf == "M15":
            bucket_minute = (now.minute // 15) * 15
            current_bar_open = now.replace(minute=bucket_minute, second=0, microsecond=0)
            return current_bar_open - timedelta(minutes=15)

        elif tf == "H1":
            current_bar_open = now.replace(minute=0, second=0, microsecond=0)
            return current_bar_open - timedelta(hours=1)

        elif tf == "H4":
            bucket_hour = (now.hour // 4) * 4
            current_bar_open = now.replace(hour=bucket_hour, minute=0, second=0, microsecond=0)
            return current_bar_open - timedelta(hours=4)

        elif tf == "D1" or tf == "D":
            current_bar_open = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return current_bar_open - timedelta(days=1)

        else:
            # Default fallback for unmapped timeframe (e.g. 15m)
            bucket_minute = (now.minute // 15) * 15
            current_bar_open = now.replace(minute=bucket_minute, second=0, microsecond=0)
            return current_bar_open - timedelta(minutes=15)

    def is_candle_stale(
        self,
        latest_closed_candle: Candle,
        now_dt: datetime | None = None,
        raise_on_stale: bool = False,
    ) -> tuple[bool, float]:
        """Check if the latest closed candle matches the expected closed candle for its timeframe.
        
        Returns:
            (is_stale, delta_seconds_from_expected)
        """
        now = now_dt or datetime.now(timezone.utc)
        expected_ts = self.get_expected_last_closed_candle_time(latest_closed_candle.timeframe, now_dt=now)

        candle_ts = latest_closed_candle.timestamp
        if candle_ts.tzinfo is None:
            candle_ts = candle_ts.replace(tzinfo=timezone.utc)
        else:
            candle_ts = candle_ts.astimezone(timezone.utc)

        # If the latest closed candle is older than expected, we missed one or more closed candles!
        is_stale = candle_ts < expected_ts
        delta_seconds = max(0.0, (expected_ts - candle_ts).total_seconds())

        if is_stale:
            logger.warning(
                "DATA_STALE: %s %s last closed candle is from %s, expected %s (lag: %.0fs)",
                latest_closed_candle.symbol,
                latest_closed_candle.timeframe,
                candle_ts.isoformat(),
                expected_ts.isoformat(),
                delta_seconds,
            )
            if raise_on_stale:
                raise StaleDataException(
                    symbol=latest_closed_candle.symbol,
                    age_seconds=delta_seconds,
                    max_age_seconds=0.0,
                )

        return is_stale, delta_seconds

    def is_quote_stale(
        self,
        quote: TickerQuote,
        now_dt: datetime | None = None,
        raise_on_stale: bool = False,
    ) -> tuple[bool, float]:
        """Check whether a real-time quote exceeds the flat 300s staleness limit."""
        now = now_dt or datetime.now(timezone.utc)
        if quote.timestamp.tzinfo is None:
            q_ts = quote.timestamp.replace(tzinfo=timezone.utc)
        else:
            q_ts = quote.timestamp.astimezone(timezone.utc)

        age = max(0.0, (now - q_ts).total_seconds())
        is_stale = age > self.max_quote_age_seconds

        if is_stale:
            logger.warning(
                "DATA_STALE quote for %s: age %.1fs exceeds threshold %.1fs",
                quote.symbol,
                age,
                self.max_quote_age_seconds,
            )
            if raise_on_stale:
                raise StaleDataException(
                    symbol=quote.symbol,
                    age_seconds=age,
                    max_age_seconds=self.max_quote_age_seconds,
                )

        return is_stale, age
