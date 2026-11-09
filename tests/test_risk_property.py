"""Property-based testing with Hypothesis for PositionSizer."""

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from trading_bot.config.models import InstrumentConfig
from trading_bot.risk.sizing import PositionSizer

# Forex EUR_USD Instrument
EUR_USD_INST = InstrumentConfig(
    symbol="EUR_USD",
    display_name="EUR/USD",
    base_currency="EUR",
    quote_currency="USD",
    pip_size=0.0001,
    contract_size=1.0,
    min_order_units=1.0,
    broker="oanda",
)

# Gold XAU_USD Instrument
XAU_USD_INST = InstrumentConfig(
    symbol="XAU_USD",
    display_name="Gold",
    base_currency="XAU",
    quote_currency="USD",
    pip_size=0.01,
    contract_size=1.0,
    min_order_units=1.0,
    broker="oanda",
)

# Crypto BTC/USD Instrument
BTC_USD_INST = InstrumentConfig(
    symbol="BTC/USD",
    display_name="Bitcoin",
    base_currency="BTC",
    quote_currency="USD",
    pip_size=0.01,
    contract_size=1.0,
    min_order_qty=0.0001,
    broker="alpaca",
)


@given(
    equity=st.floats(min_value=500.0, max_value=1_000_000.0),
    entry_price=st.floats(min_value=0.5, max_value=2.0),
    stop_distance=st.floats(min_value=0.0005, max_value=0.05),
    risk_pct=st.floats(min_value=0.002, max_value=0.02),
    max_trade_usd=st.floats(min_value=1000.0, max_value=50000.0),
)
@settings(max_examples=100)
def test_forex_sizing_properties(equity, entry_price, stop_distance, risk_pct, max_trade_usd):
    stop_loss = max(0.0001, entry_price - stop_distance)
    qty, risk_usd, err = PositionSizer.calculate_position_size(
        symbol="EUR_USD",
        entry_price=entry_price,
        stop_loss=stop_loss,
        equity=equity,
        risk_pct=risk_pct,
        instrument=EUR_USD_INST,
        max_single_trade_usd=max_trade_usd,
    )

    if err is None:
        # Invariant 1: Non-negative and integer units for Forex
        assert qty >= 1.0
        assert qty == math.floor(qty)

        # Invariant 2: Nominal trade value does not exceed max_trade_usd
        nominal_usd = qty * entry_price
        assert nominal_usd <= max_trade_usd + 1.0

        # Invariant 3: Realized risk does not exceed target risk
        target_risk = equity * risk_pct
        assert risk_usd <= target_risk + 0.05
    else:
        # If error returned, qty and risk must be 0
        assert qty == 0.0
        assert risk_usd == 0.0


@given(
    equity=st.floats(min_value=1000.0, max_value=1_000_000.0),
    entry_price=st.floats(min_value=1500.0, max_value=3500.0),
    stop_distance=st.floats(min_value=5.0, max_value=100.0),
    risk_pct=st.floats(min_value=0.002, max_value=0.02),
    max_trade_usd=st.floats(min_value=2000.0, max_value=50000.0),
)
@settings(max_examples=100)
def test_gold_sizing_properties(equity, entry_price, stop_distance, risk_pct, max_trade_usd):
    stop_loss = max(1.0, entry_price - stop_distance)
    qty, risk_usd, err = PositionSizer.calculate_position_size(
        symbol="XAU_USD",
        entry_price=entry_price,
        stop_loss=stop_loss,
        equity=equity,
        risk_pct=risk_pct,
        instrument=XAU_USD_INST,
        max_single_trade_usd=max_trade_usd,
    )

    if err is None:
        assert qty >= 1.0
        # Precision 2 decimals
        assert round(qty, 2) == qty

        nominal_usd = qty * entry_price
        assert nominal_usd <= max_trade_usd + 1.0

        target_risk = equity * risk_pct
        assert risk_usd <= target_risk + 0.05
    else:
        assert qty == 0.0
        assert risk_usd == 0.0


@given(
    equity=st.floats(min_value=500.0, max_value=1_000_000.0),
    entry_price=st.floats(min_value=10000.0, max_value=120000.0),
    stop_distance=st.floats(min_value=50.0, max_value=5000.0),
    risk_pct=st.floats(min_value=0.002, max_value=0.02),
    max_trade_usd=st.floats(min_value=1000.0, max_value=50000.0),
)
@settings(max_examples=100)
def test_crypto_sizing_properties(equity, entry_price, stop_distance, risk_pct, max_trade_usd):
    stop_loss = max(1.0, entry_price - stop_distance)
    qty, risk_usd, err = PositionSizer.calculate_position_size(
        symbol="BTC/USD",
        entry_price=entry_price,
        stop_loss=stop_loss,
        equity=equity,
        risk_pct=risk_pct,
        instrument=BTC_USD_INST,
        max_single_trade_usd=max_trade_usd,
    )

    if err is None:
        assert qty >= 0.0001
        # Step precision 0.0001 -> 4 decimals
        assert round(qty, 4) == qty

        nominal_usd = qty * entry_price
        assert nominal_usd <= max_trade_usd + 1.0

        target_risk = equity * risk_pct
        assert risk_usd <= target_risk + 0.05
    else:
        assert qty == 0.0
        assert risk_usd == 0.0
