"""Tests for timeframe-aware staleness, expected closed candle logic, and incomplete bar dropping."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from trading_bot.brokers.alpaca import AlpacaBroker
from trading_bot.brokers.models import Candle, TickerQuote
from trading_bot.brokers.oanda import OandaBroker
from trading_bot.core.exceptions import StaleDataException
from trading_bot.data.staleness import StalenessGuard


def test_quote_staleness_300s():
    guard = StalenessGuard(max_quote_age_seconds=300.0)
    now = datetime(2026, 11, 9, 14, 0, 0, tzinfo=timezone.utc)

    # 100 seconds old quote -> fresh
    fresh_quote = TickerQuote(
        symbol="EUR_USD",
        bid=1.0800,
        ask=1.0801,
        last=1.08005,
        timestamp=now - timedelta(seconds=100),
    )
    is_stale, age = guard.is_quote_stale(fresh_quote, now_dt=now)
    assert not is_stale
    assert age == 100.0

    # 350 seconds old quote -> stale!
    stale_quote = TickerQuote(
        symbol="EUR_USD",
        bid=1.0800,
        ask=1.0801,
        last=1.08005,
        timestamp=now - timedelta(seconds=350),
    )
    is_stale, age = guard.is_quote_stale(stale_quote, now_dt=now)
    assert is_stale
    assert age == 350.0

    # Test raise_on_stale flag
    with pytest.raises(StaleDataException):
        guard.is_quote_stale(stale_quote, now_dt=now, raise_on_stale=True)


def test_timeframe_aware_closed_candle_m15():
    # At 14:22 UTC, the current forming candle is 14:15 - 14:30.
    # The last CLOSED M15 candle started at 14:00 (closed at 14:15).
    now = datetime(2026, 11, 9, 14, 22, 10, tzinfo=timezone.utc)
    expected_m15 = StalenessGuard.get_expected_last_closed_candle_time("M15", now_dt=now)
    assert expected_m15 == datetime(2026, 11, 9, 14, 0, 0, tzinfo=timezone.utc)


def test_timeframe_aware_closed_candle_h1():
    # At 14:22 UTC, current forming candle is 14:00 - 15:00.
    # The last CLOSED H1 candle started at 13:00 (closed at 14:00).
    now = datetime(2026, 11, 9, 14, 22, 10, tzinfo=timezone.utc)
    expected_h1 = StalenessGuard.get_expected_last_closed_candle_time("H1", now_dt=now)
    assert expected_h1 == datetime(2026, 11, 9, 13, 0, 0, tzinfo=timezone.utc)


def test_timeframe_aware_closed_candle_h4():
    # At 14:22 UTC, current 4H bucket is 12:00 - 16:00.
    # The last CLOSED H4 candle started at 08:00 (closed at 12:00).
    now = datetime(2026, 11, 9, 14, 22, 10, tzinfo=timezone.utc)
    expected_h4 = StalenessGuard.get_expected_last_closed_candle_time("H4", now_dt=now)
    assert expected_h4 == datetime(2026, 11, 9, 8, 0, 0, tzinfo=timezone.utc)


def test_timeframe_aware_closed_candle_d1():
    # At 14:22 UTC on Nov 9, current forming D1 candle is Nov 9 00:00 - Nov 10 00:00.
    # The last CLOSED D1 candle opened on Nov 8 00:00 (closed on Nov 9 00:00).
    now = datetime(2026, 11, 9, 14, 22, 10, tzinfo=timezone.utc)
    expected_d1 = StalenessGuard.get_expected_last_closed_candle_time("D1", now_dt=now)
    assert expected_d1 == datetime(2026, 11, 8, 0, 0, 0, tzinfo=timezone.utc)


def test_candle_staleness_h4_and_d1():
    guard = StalenessGuard()
    now = datetime(2026, 11, 9, 14, 22, 10, tzinfo=timezone.utc)

    # Valid H4 closed candle (from 08:00 UTC) -> FRESH even though it opened 6 hours ago!
    # A naive 300s check would fail, but our timeframe-aware guard correctly identifies it as fresh!
    h4_candle = Candle(
        symbol="EUR_USD",
        timeframe="H4",
        timestamp=datetime(2026, 11, 9, 8, 0, 0, tzinfo=timezone.utc),
        open=1.08, high=1.085, low=1.079, close=1.082, volume=1000, complete=True,
    )
    is_stale, delta = guard.is_candle_stale(h4_candle, now_dt=now)
    assert not is_stale
    assert delta == 0.0

    # Outdated H4 candle (from 04:00 UTC) -> STALE!
    h4_stale = Candle(
        symbol="EUR_USD",
        timeframe="H4",
        timestamp=datetime(2026, 11, 9, 4, 0, 0, tzinfo=timezone.utc),
        open=1.08, high=1.085, low=1.079, close=1.082, volume=1000, complete=True,
    )
    is_stale, delta = guard.is_candle_stale(h4_stale, now_dt=now)
    assert is_stale
    assert delta == 4 * 3600  # 4 hours behind

    # Valid D1 closed candle (from Nov 8 00:00 UTC) -> FRESH even though it opened 38 hours ago!
    d1_candle = Candle(
        symbol="BTC/USD",
        timeframe="D1",
        timestamp=datetime(2026, 11, 8, 0, 0, 0, tzinfo=timezone.utc),
        open=60000, high=61000, low=59500, close=60500, volume=500, complete=True,
    )
    is_stale, delta = guard.is_candle_stale(d1_candle, now_dt=now)
    assert not is_stale
    assert delta == 0.0


@pytest.mark.asyncio
async def test_oanda_drops_incomplete_candles():
    # OANDA API returns complete=True and complete=False bars
    mock_resp = {
        "candles": [
            {
                "complete": True,
                "time": "2026-11-09T13:45:00.000000000Z",
                "mid": {"o": "1.0800", "h": "1.0820", "l": "1.0795", "c": "1.0810"},
                "volume": 450,
            },
            {
                "complete": False,  # Forming bar -> MUST BE DROPPED
                "time": "2026-11-09T14:00:00.000000000Z",
                "mid": {"o": "1.0810", "h": "1.0815", "l": "1.0805", "c": "1.0812"},
                "volume": 120,
            },
        ]
    }

    def handler(request):
        import httpx
        return httpx.Response(200, json=mock_resp)

    import httpx
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    broker = OandaBroker(account_id="test_acc", api_token="test_tok", http_client=client)
    candles = await broker.get_candles("EUR_USD", timeframe="M15", count=2)

    # Only the completed bar must be returned!
    assert len(candles) == 1
    assert candles[0].complete is True
    assert candles[0].open == 1.0800


@pytest.mark.asyncio
async def test_alpaca_drops_forming_bar():
    # In Alpaca Crypto API, a forming bar timestamp + timeframe_delta extends past now_utc
    now = datetime(2026, 11, 9, 14, 22, 0, tzinfo=timezone.utc)
    mock_resp = {
        "bars": {
            "BTC/USD": [
                {
                    "t": "2026-11-09T14:00:00Z",  # Completed 14:00 - 14:15 bar (ends 14:15 <= 14:22)
                    "o": 60000.0, "h": 60500.0, "l": 59900.0, "c": 60200.0, "v": 15.5,
                },
                {
                    "t": "2026-11-09T14:15:00Z",  # Forming bar 14:15 - 14:30 (ends 14:30 > 14:22) -> MUST BE DROPPED!
                    "o": 60200.0, "h": 60300.0, "l": 60100.0, "c": 60250.0, "v": 3.2,
                },
            ]
        }
    }

    def handler(request):
        import httpx
        return httpx.Response(200, json=mock_resp)

    import httpx
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    broker = AlpacaBroker(api_key="key", secret_key="sec", http_client=client)

    with patch("trading_bot.brokers.alpaca.datetime") as mock_dt:
        mock_dt.now.return_value = now
        mock_dt.fromisoformat = datetime.fromisoformat
        candles = await broker.get_candles("BTC/USD", timeframe="M15", count=2)

        # Only completed bar is returned
        assert len(candles) == 1
        assert candles[0].open == 60000.0
