"""Deterministic position sizing engine per instrument type with exact currency conversions."""

import math
from collections.abc import Mapping

from trading_bot.config.models import InstrumentConfig


def get_quote_to_usd_rate(quote_currency: str, current_prices: Mapping[str, float] | None = None) -> float:
    """Resolve conversion rate from quote currency to account currency (USD).
    
    Returns multiplier such that: value_in_usd = value_in_quote * rate.
    """
    quote = quote_currency.upper().strip()
    if quote == "USD":
        return 1.0

    prices = current_prices or {}

    # Check direct quotes: e.g. GBP -> GBP_USD or GBP/USD
    direct_keys = [f"{quote}_USD", f"{quote}/USD"]
    for k in direct_keys:
        if k in prices and prices[k] > 0:
            return float(prices[k])

    # Check inverse quotes: e.g. JPY -> USD_JPY or USD/JPY
    inverse_keys = [f"USD_{quote}", f"USD/{quote}"]
    for k in inverse_keys:
        if k in prices and prices[k] > 0:
            return 1.0 / float(prices[k])

    # Standard default baseline exchange rates if live conversion quote not provided
    fallbacks = {
        "JPY": 1.0 / 150.0,
        "CHF": 1.0 / 0.90,
        "CAD": 1.0 / 1.35,
        "GBP": 1.25,
        "EUR": 1.08,
        "AUD": 0.65,
        "NZD": 0.60,
    }
    return fallbacks.get(quote, 1.0)


class PositionSizer:
    """Calculates maximum compliant order size for Forex, Metals, and Crypto."""

    @staticmethod
    def calculate_position_size(
        symbol: str,
        entry_price: float,
        stop_loss: float,
        equity: float,
        risk_pct: float,
        instrument: InstrumentConfig,
        current_prices: Mapping[str, float] | None = None,
        max_single_trade_usd: float = 10000.0,
    ) -> tuple[float, float, str | None]:
        """Compute position size strictly rounded DOWN to broker precision.
        
        Returns:
            (approved_quantity, risk_usd, rejection_reason_if_any)
        """
        if equity <= 0:
            return 0.0, 0.0, "EQUITY_NON_POSITIVE"

        stop_distance = abs(entry_price - stop_loss)
        if stop_distance <= 0:
            return 0.0, 0.0, "ZERO_STOP_DISTANCE"

        target_risk_usd = equity * risk_pct
        quote_to_usd = get_quote_to_usd_rate(instrument.quote_currency, current_prices=current_prices)

        # -------------------------------------------------------------
        # 1. Raw Position Sizing per Instrument Type
        # -------------------------------------------------------------
        if instrument.is_crypto:
            # Spot Crypto (e.g. BTC/USD): raw_qty = risk_usd / stop_distance
            raw_qty = target_risk_usd / stop_distance
            step = instrument.min_order_qty or 0.0001
            # Round DOWN to broker precision step
            precision_decimals = max(0, -int(math.floor(math.log10(step)))) if step < 1 else 0
            multiplier = 10**precision_decimals
            quantity = math.floor(raw_qty * multiplier) / multiplier

            min_order = instrument.min_order_qty or 0.0001
            if quantity < min_order:
                return 0.0, 0.0, f"MIN_ORDER_SIZE_VIOLATION: Sized {quantity} below min order {min_order}"

        elif instrument.is_gold:
            # Gold XAU/USD (CFD): contract_size=1.0 oz. Stop distance is in USD per oz.
            # raw_units = risk_usd / stop_distance
            raw_units = target_risk_usd / stop_distance
            # Round down to 2 decimals
            quantity = math.floor(raw_units * 100.0) / 100.0
            min_units = instrument.min_order_units or 1.0
            if quantity < min_units:
                return 0.0, 0.0, f"MIN_ORDER_SIZE_VIOLATION: Sized {quantity} below min units {min_units}"

        else:
            # Standard Forex (Majors & Crosses)
            # Dollar risk per unit: stop_distance * quote_to_usd
            # For EUR_USD: stop_distance * 1.0
            # For USD_JPY: stop_distance * (1 / USD_JPY) = stop_distance / entry_price
            # For EUR_GBP: stop_distance * GBP_USD
            risk_per_unit_usd = stop_distance * quote_to_usd
            if risk_per_unit_usd <= 0:
                return 0.0, 0.0, "INVALID_RISK_PER_UNIT"

            raw_units = target_risk_usd / risk_per_unit_usd
            # OANDA Forex order units must be integer units -> ALWAYS round down!
            quantity = float(math.floor(raw_units))
            min_units = instrument.min_order_units or 1.0
            if quantity < min_units:
                return 0.0, 0.0, f"MIN_ORDER_SIZE_VIOLATION: Sized {quantity:.0f} below min units {min_units}"

        # -------------------------------------------------------------
        # 2. Maximum Single Trade Size USD Cap
        # -------------------------------------------------------------
        nominal_usd = quantity * entry_price
        if nominal_usd > max_single_trade_usd:
            # Cap quantity down to max single trade size
            capped_raw = max_single_trade_usd / entry_price
            if instrument.is_crypto:
                step = instrument.min_order_qty or 0.0001
                precision_decimals = max(0, -int(math.floor(math.log10(step)))) if step < 1 else 0
                multiplier = 10**precision_decimals
                quantity = math.floor(capped_raw * multiplier) / multiplier
                if quantity < (instrument.min_order_qty or 0.0001):
                    return 0.0, 0.0, "MAX_TRADE_CAP_FORCES_SUB_MIN_ORDER"
            elif instrument.is_gold:
                quantity = math.floor(capped_raw * 100.0) / 100.0
                if quantity < (instrument.min_order_units or 1.0):
                    return 0.0, 0.0, "MAX_TRADE_CAP_FORCES_SUB_MIN_ORDER"
            else:
                quantity = float(math.floor(capped_raw))
                if quantity < (instrument.min_order_units or 1.0):
                    return 0.0, 0.0, "MAX_TRADE_CAP_FORCES_SUB_MIN_ORDER"

        # -------------------------------------------------------------
        # 3. Calculate Final Realized Risk USD
        # -------------------------------------------------------------
        if instrument.is_crypto or instrument.is_gold:
            realized_risk_usd = round(quantity * stop_distance, 2)
        else:
            realized_risk_usd = round(quantity * stop_distance * quote_to_usd, 2)

        return quantity, realized_risk_usd, None


def calculate_position_size(
    symbol: str,
    entry_price: float,
    stop_loss: float,
    equity: float,
    risk_pct: float,
    instrument: InstrumentConfig,
    current_prices: Mapping[str, float] | None = None,
    max_single_trade_usd: float = 10000.0,
) -> tuple[float, float, str | None]:
    """Convenience wrapper for PositionSizer.calculate_position_size."""
    return PositionSizer.calculate_position_size(
        symbol=symbol,
        entry_price=entry_price,
        stop_loss=stop_loss,
        equity=equity,
        risk_pct=risk_pct,
        instrument=instrument,
        current_prices=current_prices,
        max_single_trade_usd=max_single_trade_usd,
    )
