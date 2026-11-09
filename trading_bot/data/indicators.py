"""Technical indicators engine: EMA stack, RSI, ATR, VWAP, Bollinger Bands, MACD, and Pivots."""

from collections.abc import Sequence
from datetime import datetime, timezone

import numpy as np

from trading_bot.brokers.models import Candle
from trading_bot.data.models import (
    BollingerBandsResult,
    EmaStack,
    IndicatorsResult,
    MacdResult,
    PivotPoints,
    Timeframe,
)


def compute_ema(series: Sequence[float], span: int) -> list[float]:
    """Calculate Exponential Moving Average with smoothing multiplier 2/(span+1)."""
    if not series:
        return []
    if len(series) < span:
        # Fallback to simple average if series is short
        return [float(np.mean(series))] * len(series)

    k = 2.0 / (span + 1)
    ema_values: list[float] = [float(series[0])]
    for price in series[1:]:
        ema_values.append(price * k + ema_values[-1] * (1 - k))
    return ema_values


def compute_rsi(closes: Sequence[float], period: int = 14) -> float:
    """Calculate Relative Strength Index (RSI) using Wilder's smoothing."""
    if len(closes) < period + 1:
        return 50.0  # Neutral fallback on insufficient data

    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    # Initial average
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0 else 50.0

    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def compute_atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> float:
    """Calculate Average True Range (ATR)."""
    if len(closes) < 2:
        return 0.0

    tr_list: list[float] = []
    for i in range(1, len(closes)):
        h = highs[i]
        low_val = lows[i]
        prev_c = closes[i - 1]
        tr = max(h - low_val, abs(h - prev_c), abs(low_val - prev_c))
        tr_list.append(tr)

    if not tr_list:
        return 0.0

    if len(tr_list) < period:
        return float(np.mean(tr_list))

    # Wilder smoothing
    atr = float(np.mean(tr_list[:period]))
    for tr in tr_list[period:]:
        atr = (atr * (period - 1) + tr) / period

    return round(atr, 5)


def compute_vwap(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
) -> float | None:
    """Calculate Volume Weighted Average Price (VWAP)."""
    if not closes or not volumes or sum(volumes) == 0:
        return None

    typical_prices = [(h + lo + c) / 3.0 for h, lo, c in zip(highs, lows, closes, strict=False)]
    cum_pv = sum(tp * v for tp, v in zip(typical_prices, volumes, strict=False))
    cum_vol = sum(volumes)
    return round(cum_pv / cum_vol, 5) if cum_vol > 0 else None


def compute_bollinger_bands(
    closes: Sequence[float],
    period: int = 20,
    num_std: float = 2.0,
) -> BollingerBandsResult:
    """Calculate Bollinger Bands (20, 2.0)."""
    if len(closes) < period:
        # Fallback using available closes
        avg = float(np.mean(closes))
        std = float(np.std(closes)) if len(closes) > 1 else 0.001
    else:
        window = closes[-period:]
        avg = float(np.mean(window))
        std = float(np.std(window))

    upper = avg + num_std * std
    lower = avg - num_std * std
    bandwidth = (upper - lower) / avg if avg > 0 else 0.0
    latest_close = closes[-1] if closes else avg
    percent_b = (latest_close - lower) / (upper - lower) if (upper - lower) > 0 else 0.5

    return BollingerBandsResult(
        upper=round(upper, 5),
        middle=round(avg, 5),
        lower=round(lower, 5),
        bandwidth=round(bandwidth, 4),
        percent_b=round(percent_b, 4),
    )


def compute_macd(
    closes: Sequence[float],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> MacdResult:
    """Calculate Moving Average Convergence Divergence (MACD)."""
    if len(closes) < slow + signal_period:
        return MacdResult(macd=0.0, signal=0.0, histogram=0.0)

    fast_ema = compute_ema(closes, fast)
    slow_ema = compute_ema(closes, slow)
    macd_line = [f - s for f, s in zip(fast_ema, slow_ema, strict=False)]
    signal_line = compute_ema(macd_line, signal_period)

    current_macd = macd_line[-1]
    current_signal = signal_line[-1]
    hist = current_macd - current_signal

    return MacdResult(
        macd=round(current_macd, 5),
        signal=round(current_signal, 5),
        histogram=round(hist, 5),
    )


def compute_pivots(high: float, low: float, close: float) -> PivotPoints:
    """Calculate Classical Daily Pivot Points (P, R1, R2, S1, S2)."""
    pivot = (high + low + close) / 3.0
    r1 = (2.0 * pivot) - low
    s1 = (2.0 * pivot) - high
    r2 = pivot + (high - low)
    s2 = pivot - (high - low)

    return PivotPoints(
        pivot=round(pivot, 5),
        r1=round(r1, 5),
        r2=round(r2, 5),
        s1=round(s1, 5),
        s2=round(s2, 5),
    )


def compute_volume_metrics(
    closes: Sequence[float],
    volumes: Sequence[float],
    period: int = 20,
) -> tuple[float, float, bool]:
    """Calculate volume delta and check for volume spike.
    
    Returns:
        (volume_delta, volume_spike_ratio, is_volume_spike)
    """
    if not volumes or len(volumes) < 2:
        return 0.0, 1.0, False

    # Volume delta estimate: up candle vol - down candle vol over recent 5 bars
    lookback = min(5, len(closes) - 1)
    up_vol = 0.0
    down_vol = 0.0
    for i in range(-lookback, 0):
        if closes[i] >= closes[i - 1]:
            up_vol += volumes[i]
        else:
            down_vol += volumes[i]
    total = up_vol + down_vol
    vol_delta = (up_vol - down_vol) / total if total > 0 else 0.0

    # Volume spike ratio
    current_vol = volumes[-1]
    window = volumes[-period:-1] if len(volumes) > period else volumes[:-1]
    avg_vol = float(np.mean(window)) if window else current_vol
    spike_ratio = current_vol / avg_vol if avg_vol > 0 else 1.0
    is_spike = spike_ratio >= 1.5

    return round(vol_delta, 3), round(spike_ratio, 2), is_spike


def compute_all_indicators(
    symbol: str,
    candles: list[Candle],
    timeframe: Timeframe = Timeframe.M15,
    daily_candle: Candle | None = None,
) -> IndicatorsResult:
    """Compute complete indicator suite from a list of candles."""
    if not candles:
        raise ValueError(f"Cannot compute indicators for {symbol}: candle list is empty.")

    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    volumes = [c.volume for c in candles]

    latest_close = closes[-1]
    rsi = compute_rsi(closes, period=14)
    atr = compute_atr(highs, lows, closes, period=14)
    vwap = compute_vwap(highs, lows, closes, volumes)
    vwap_distance_pct = ((latest_close - vwap) / vwap * 100.0) if vwap else None

    # EMAs
    ema_9 = compute_ema(closes, 9)[-1]
    ema_21 = compute_ema(closes, 21)[-1]
    ema_50 = compute_ema(closes, 50)[-1]
    ema_200 = compute_ema(closes, 200)[-1] if len(closes) >= 50 else None

    ema_stack = EmaStack(
        ema_9=round(ema_9, 5),
        ema_21=round(ema_21, 5),
        ema_50=round(ema_50, 5),
        ema_200=round(ema_200, 5) if ema_200 is not None else None,
    )

    bollinger = compute_bollinger_bands(closes, period=20, num_std=2.0)
    macd = compute_macd(closes, fast=12, slow=26, signal_period=9)

    # Pivots from daily candle or recent 24h range
    if daily_candle is not None:
        pivots = compute_pivots(daily_candle.high, daily_candle.low, daily_candle.close)
    else:
        recent_h = max(highs[-96:]) if len(highs) >= 96 else max(highs)
        recent_l = min(lows[-96:]) if len(lows) >= 96 else min(lows)
        pivots = compute_pivots(recent_h, recent_l, latest_close)

    vol_delta, spike_ratio, is_spike = compute_volume_metrics(closes, volumes)

    # Trend classification
    if ema_stack.is_bullish_aligned and rsi > 50 and macd.histogram > 0:
        trend = "BULLISH"
    elif ema_stack.is_bearish_aligned and rsi < 50 and macd.histogram < 0:
        trend = "BEARISH"
    else:
        trend = "NEUTRAL"

    return IndicatorsResult(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=candles[-1].timestamp if candles else datetime.now(timezone.utc),
        latest_close=latest_close,
        rsi=rsi,
        atr=atr,
        vwap=vwap,
        vwap_distance_pct=round(vwap_distance_pct, 3) if vwap_distance_pct is not None else None,
        ema_stack=ema_stack,
        bollinger=bollinger,
        macd=macd,
        pivots=pivots,
        volume_delta=vol_delta,
        volume_spike_ratio=spike_ratio,
        is_volume_spike=is_spike,
        trend_direction=trend,
    )
