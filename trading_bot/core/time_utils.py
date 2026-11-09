import re
from datetime import datetime, timezone


def parse_iso_datetime(time_str: str) -> datetime:
    """Safely parse ISO8601 strings handling Z, offsets, and nanosecond precision in Python 3.10+."""
    clean = time_str.strip().replace("Z", "+00:00")
    # Truncate sub-second fractions greater than 6 digits (nanoseconds) to 6 digits (microseconds)
    clean = re.sub(r"(\.\d{6})\d+", r"\1", clean)
    dt = datetime.fromisoformat(clean)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def utc_now() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def is_forex_market_open(
    dt: datetime | None = None,
    close_day: int = 4,     # Friday (0=Mon, 4=Fri)
    close_hour: int = 21,
    close_minute: int = 0,
    reopen_day: int = 6,    # Sunday (6=Sun)
    reopen_hour: int = 21,
    reopen_minute: int = 0,
) -> bool:
    """Check if the Forex market is currently open.
    
    Standard Forex session closes Friday 21:00 UTC and reopens Sunday 21:00 UTC.
    During this period, the market is CLOSED.
    """
    check_time = dt or utc_now()
    if check_time.tzinfo is None:
        check_time = check_time.replace(tzinfo=timezone.utc)
    else:
        check_time = check_time.astimezone(timezone.utc)

    weekday = check_time.weekday()  # Monday is 0, Sunday is 6
    hour = check_time.hour
    minute = check_time.minute
    time_minutes = hour * 60 + minute

    close_minutes = close_hour * 60 + close_minute
    reopen_minutes = reopen_hour * 60 + reopen_minute

    # Friday after close
    if weekday == close_day and time_minutes >= close_minutes:
        return False
    # All of Saturday
    if weekday == 5:
        return False
    # Sunday before reopen
    return not (weekday == reopen_day and time_minutes < reopen_minutes)


def is_crypto_market_open() -> bool:
    """Crypto markets trade 24/7."""
    return True


def is_candle_close_aligned(dt: datetime | None = None, interval_minutes: int = 15, tolerance_seconds: int = 45) -> bool:
    """Check if current time is within tolerance of candle close."""
    now = dt or utc_now()
    minute = now.minute
    second = now.second
    seconds_past_hour = minute * 60 + second
    interval_seconds = interval_minutes * 60

    remainder = seconds_past_hour % interval_seconds
    return remainder <= tolerance_seconds or (interval_seconds - remainder) <= tolerance_seconds


def seconds_until_next_candle(dt: datetime | None = None, interval_minutes: int = 15) -> int:
    """Calculate remaining seconds until the next aligned candle boundary."""
    now = dt or utc_now()
    minute = now.minute
    second = now.second
    seconds_past_hour = minute * 60 + second
    interval_seconds = interval_minutes * 60
    remainder = seconds_past_hour % interval_seconds
    return interval_seconds - remainder if remainder != 0 else interval_seconds
