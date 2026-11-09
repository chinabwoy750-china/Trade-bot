"""Deterministic, AI-free Risk Management Engine enforcing strict mathematical capital guardrails."""

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from trading_bot.brokers.models import OrderSide, Position
from trading_bot.config.models import AppConfig, InstrumentConfig
from trading_bot.decision.models import ActionType, TradeDecision
from trading_bot.risk.models import RiskCheckResult, RiskVetoReason
from trading_bot.risk.sizing import PositionSizer, get_quote_to_usd_rate
from trading_bot.storage.repository import StorageRepository

logger = logging.getLogger("trading_bot.risk.manager")


class DeterministicRiskManager:
    """Production-grade deterministic risk controller.
    
    The AI decision agent proposes; this class deterministically validates and sizes.
    Has absolute veto power over every proposed trade. Contains zero AI.
    """

    def __init__(
        self,
        config: AppConfig,
        repository: StorageRepository | None = None,
    ) -> None:
        self.config = config
        self.limits = config.risk.limits
        self.allocation = config.risk.capital_allocation
        self.exposure_caps = config.risk.currency_exposure_caps
        self.safety = config.risk.safety_halts
        self.spread_limits = config.risk.spread_and_slippage
        self.repository = repository or StorageRepository(config.settings.database.url)

    # -------------------------------------------------------------------------
    # Persistent State & System Safety Checks
    # -------------------------------------------------------------------------
    def is_system_halted(self) -> tuple[bool, str | None, RiskVetoReason | None]:
        """Check whether the system is halted due to persistent killswitch or loss halts."""
        state = self.repository.get_or_create_system_state()
        if state.killswitch_active:
            return True, "Emergency killswitch is active in persistent state", RiskVetoReason.KILLSWITCH_ACTIVE
        if state.is_halted:
            reason_str = state.halt_reason or "System halt active"
            if "CONSECUTIVE_LOSS" in reason_str:
                return True, reason_str, RiskVetoReason.CONSECUTIVE_LOSS_HALT
            return True, reason_str, RiskVetoReason.GLOBAL_DAILY_LOSS_HALT
        return False, None, None

    def activate_killswitch(self, reason: str = "Manual killswitch activated") -> None:
        """Manually trigger emergency killswitch and persist state across restarts."""
        logger.warning(f"KILLSWITCH ACTIVATED: {reason}")
        self.repository.set_killswitch(active=True)

    def deactivate_killswitch(self) -> None:
        """Manually deactivate emergency killswitch."""
        logger.info("KILLSWITCH DEACTIVATED by manual command")
        self.repository.set_killswitch(active=False)

    def reset_halt(self) -> None:
        """Clear persistent system halts and reset consecutive losses after manual review."""
        logger.info("SYSTEM HALT RESET by manual operator command")
        self.repository.clear_system_halt()

    def record_trade_result(self, is_win: bool) -> int:
        """Record trade win/loss and update persistent consecutive loss tracker.
        
        If consecutive losses reach or exceed max_consecutive_losses, triggers persistent halt.
        """
        consecutive = self.repository.record_trade_outcome(is_win=is_win)
        if consecutive >= self.safety.max_consecutive_losses:
            reason = (
                f"CONSECUTIVE_LOSS_HALT: {consecutive} consecutive losses reached "
                f"(limit: {self.safety.max_consecutive_losses})"
            )
            logger.error(reason)
            self.repository.set_system_halt(reason=reason)
        return consecutive

    def check_daily_loss_halt(
        self,
        current_equity: float,
        now_utc: datetime | None = None,
    ) -> tuple[bool, str | None]:
        """Evaluate start-of-day equity vs current equity (including unrealized PnL).
        
        Boundary: 00:00 UTC of current day.
        """
        dt = now_utc or datetime.now(timezone.utc)
        date_str = dt.strftime("%Y-%m-%d")
        daily_record = self.repository.get_or_create_daily_performance(
            starting_equity=current_equity,
            date_str=date_str,
        )

        starting_equity = daily_record.starting_equity
        if starting_equity <= 0:
            return False, None

        daily_drawdown_usd = starting_equity - current_equity
        daily_drawdown_pct = daily_drawdown_usd / starting_equity

        if daily_drawdown_pct >= self.safety.global_daily_loss_limit_pct:
            msg = (
                f"GLOBAL_DAILY_LOSS_HALT: Current drawdown {daily_drawdown_pct:.2%} (${daily_drawdown_usd:.2f}) "
                f"exceeds limit {self.safety.global_daily_loss_limit_pct:.2%} "
                f"(start equity: ${starting_equity:.2f}, current: ${current_equity:.2f})"
            )
            logger.error(msg)
            self.repository.set_system_halt(reason=msg)
            return True, msg

        return False, None

    # -------------------------------------------------------------------------
    # Core Trade Proposal Validation
    # -------------------------------------------------------------------------
    def validate_trade(
        self,
        proposal: TradeDecision,
        current_price: float,
        current_spread: float,
        account_equity: float,
        open_positions: Sequence[Position] | None = None,
        current_prices: Mapping[str, float] | None = None,
        daily_orders_placed_usd: float = 0.0,
        now_utc: datetime | None = None,
    ) -> RiskCheckResult:
        """Perform comprehensive deterministic validation on a proposed trade."""
        symbol = proposal.symbol
        positions = list(open_positions or [])
        prices = dict(current_prices or {})
        prices[symbol] = current_price

        # Helper to veto and persist
        def _veto(
            reason_code: RiskVetoReason,
            message: str,
            details: dict[str, Any],
        ) -> RiskCheckResult:
            logger.warning(f"RISK VETO [{reason_code.value}] {symbol}: {message} | Details: {details}")
            self.repository.save_risk_veto(
                rule_name=reason_code.value,
                symbol=symbol,
                proposed_action=proposal.action.value,
                reason=message,
                details=details,
            )
            return RiskCheckResult(
                is_approved=False,
                veto_reason=reason_code,
                reason_message=message,
                approved_quantity=0.0,
                calculated_risk_usd=0.0,
                details=details,
            )

        # 1. Persistent System Guardrail State & Killswitch
        is_halted, halt_msg, halt_reason = self.is_system_halted()
        if is_halted:
            return _veto(
                halt_reason or RiskVetoReason.KILLSWITCH_ACTIVE,
                f"Trading halted: {halt_msg}",
                {"persistent_halt": True, "message": halt_msg},
            )

        # 2. Global Daily Loss Limit Check
        daily_loss_tripped, daily_loss_msg = self.check_daily_loss_halt(account_equity, now_utc=now_utc)
        if daily_loss_tripped:
            return _veto(
                RiskVetoReason.GLOBAL_DAILY_LOSS_HALT,
                daily_loss_msg or "Daily loss limit exceeded",
                {"account_equity": account_equity},
            )

        # 3. Lookup Instrument Config
        instrument = self.config.instruments.get_instrument(symbol)
        if not instrument:
            # Try matching with standard separators
            norm_symbol = symbol.replace("/", "_")
            instrument = self.config.instruments.get_instrument(norm_symbol)
            if not instrument:
                return _veto(
                    RiskVetoReason.MIN_ORDER_SIZE_VIOLATION,
                    f"Unknown instrument '{symbol}' not found in configuration",
                    {"symbol": symbol},
                )

        # 4. Crypto Spot Long-Only Rule
        if instrument.is_crypto and proposal.action == ActionType.SELL:
            return _veto(
                RiskVetoReason.CRYPTO_SPOT_LONG_ONLY,
                f"Short selling spot crypto '{symbol}' is forbidden; spot crypto is strictly long-only",
                {"symbol": symbol, "action": proposal.action.value},
            )

        # 5. Directional Stop-Loss Validity
        entry = current_price if proposal.limit_price is None else proposal.limit_price
        sl = proposal.stop_loss
        tp = proposal.take_profit

        if proposal.action == ActionType.BUY:
            if sl >= entry:
                return _veto(
                    RiskVetoReason.INVALID_STOP_PLACEMENT,
                    f"BUY order stop-loss ({sl}) must be strictly below entry price ({entry})",
                    {"entry": entry, "stop_loss": sl, "action": "BUY"},
                )
            if tp <= entry:
                return _veto(
                    RiskVetoReason.MIN_RR_VIOLATION,
                    f"BUY order take-profit ({tp}) must be strictly above entry price ({entry})",
                    {"entry": entry, "take_profit": tp, "action": "BUY"},
                )
        elif proposal.action == ActionType.SELL:
            if sl <= entry:
                return _veto(
                    RiskVetoReason.INVALID_STOP_PLACEMENT,
                    f"SELL order stop-loss ({sl}) must be strictly above entry price ({entry})",
                    {"entry": entry, "stop_loss": sl, "action": "SELL"},
                )
            if tp >= entry:
                return _veto(
                    RiskVetoReason.MIN_RR_VIOLATION,
                    f"SELL order take-profit ({tp}) must be strictly below entry price ({entry})",
                    {"entry": entry, "take_profit": tp, "action": "SELL"},
                )

        # 6. Risk-to-Reward Ratio Check
        stop_dist = abs(entry - sl)
        target_dist = abs(tp - entry)
        if stop_dist <= 0:
            return _veto(
                RiskVetoReason.INVALID_STOP_PLACEMENT,
                "Stop distance is zero or negative",
                {"stop_distance": stop_dist},
            )
        rr = target_dist / stop_dist
        if round(rr, 4) < self.limits.min_risk_reward_ratio:
            return _veto(
                RiskVetoReason.MIN_RR_VIOLATION,
                f"Trade R:R ratio ({rr:.2f}) is below minimum requirement ({self.limits.min_risk_reward_ratio:.2f})",
                {"risk_distance": stop_dist, "target_distance": target_dist, "rr": rr, "min_rr": self.limits.min_risk_reward_ratio},
            )

        # 7. Spread & Slippage Checks
        spread_to_stop_ratio = current_spread / stop_dist
        if spread_to_stop_ratio > self.spread_limits.max_spread_to_stop_ratio:
            return _veto(
                RiskVetoReason.SPREAD_EXCEEDS_STOP_RATIO,
                f"Spread ({current_spread:.5f}) is {spread_to_stop_ratio:.1%} of stop distance ({stop_dist:.5f}), "
                f"exceeding max allowable {self.spread_limits.max_spread_to_stop_ratio:.1%}",
                {"spread": current_spread, "stop_distance": stop_dist, "spread_ratio": spread_to_stop_ratio},
            )

        if instrument.is_forex:
            pip_size = instrument.pip_size or 0.0001
            spread_pips = current_spread / pip_size
            if spread_pips > self.spread_limits.max_forex_spread_pips:
                return _veto(
                    RiskVetoReason.EXCESSIVE_FOREX_SPREAD,
                    f"Forex spread ({spread_pips:.1f} pips) exceeds maximum allowable ({self.spread_limits.max_forex_spread_pips:.1f} pips)",
                    {"spread_pips": spread_pips, "max_pips": self.spread_limits.max_forex_spread_pips},
                )
        elif instrument.is_crypto:
            spread_pct = current_spread / entry
            if spread_pct > self.spread_limits.max_crypto_spread_pct:
                return _veto(
                    RiskVetoReason.EXCESSIVE_CRYPTO_SPREAD,
                    f"Crypto spread ({spread_pct:.2%}) exceeds maximum allowable ({self.spread_limits.max_crypto_spread_pct:.2%})",
                    {"spread_pct": spread_pct, "max_spread_pct": self.spread_limits.max_crypto_spread_pct},
                )

        # 8. Check Existing Position on Symbol: No Averaging Down & No Widening Stops
        for pos in positions:
            if pos.symbol == symbol:
                pos_side = ActionType.BUY if pos.side == OrderSide.BUY else ActionType.SELL
                if proposal.action == pos_side:
                    # Check averaging down
                    if pos_side == ActionType.BUY and entry < pos.entry_price:
                        return _veto(
                            RiskVetoReason.AVERAGING_DOWN_FORBIDDEN,
                            f"Averaging down on losing BUY position in '{symbol}' is forbidden "
                            f"(entry: {entry} < current pos avg: {pos.entry_price})",
                            {"entry": entry, "existing_entry": pos.entry_price},
                        )
                    elif pos_side == ActionType.SELL and entry > pos.entry_price:
                        return _veto(
                            RiskVetoReason.AVERAGING_DOWN_FORBIDDEN,
                            f"Averaging down on losing SELL position in '{symbol}' is forbidden "
                            f"(entry: {entry} > current pos avg: {pos.entry_price})",
                            {"entry": entry, "existing_entry": pos.entry_price},
                        )

        # 9. Maximum Open Position Counts
        forex_count = sum(1 for p in positions if not self._is_crypto_symbol(p.symbol))
        crypto_count = sum(1 for p in positions if self._is_crypto_symbol(p.symbol))
        total_count = len(positions)

        if total_count >= self.limits.max_open_positions_total:
            return _veto(
                RiskVetoReason.MAX_TOTAL_POSITIONS,
                f"Maximum total positions reached ({total_count}/{self.limits.max_open_positions_total})",
                {"total_positions": total_count, "limit": self.limits.max_open_positions_total},
            )

        if instrument.is_crypto:
            if crypto_count >= self.limits.max_open_positions_crypto:
                return _veto(
                    RiskVetoReason.MAX_CRYPTO_POSITIONS,
                    f"Maximum crypto positions reached ({crypto_count}/{self.limits.max_open_positions_crypto})",
                    {"crypto_positions": crypto_count, "limit": self.limits.max_open_positions_crypto},
                )
        else:
            if forex_count >= self.limits.max_open_positions_forex:
                return _veto(
                    RiskVetoReason.MAX_FOREX_POSITIONS,
                    f"Maximum forex positions reached ({forex_count}/{self.limits.max_open_positions_forex})",
                    {"forex_positions": forex_count, "limit": self.limits.max_open_positions_forex},
                )

        # 10. Position Sizing Computation
        # Risk percentage scaled by AI confidence if between min and max risk pct
        base_risk_pct = self.limits.max_risk_per_trade_pct
        if proposal.confidence is not None and proposal.confidence < 0.6:
            base_risk_pct = self.limits.min_risk_per_trade_pct

        computed_qty, calculated_risk_usd, sizing_error = PositionSizer.calculate_position_size(
            symbol=symbol,
            entry_price=entry,
            stop_loss=sl,
            equity=account_equity,
            risk_pct=base_risk_pct,
            instrument=instrument,
            current_prices=prices,
            max_single_trade_usd=self.limits.max_single_trade_usd,
        )

        if sizing_error:
            return _veto(
                RiskVetoReason.MIN_ORDER_SIZE_VIOLATION,
                f"Position sizing rejected: {sizing_error}",
                {"error": sizing_error, "equity": account_equity, "risk_pct": base_risk_pct},
            )

        # Check if proposed quantity exceeds mathematically computed maximum
        if proposal.quantity is not None and proposal.quantity > (computed_qty * 1.001):
            return _veto(
                RiskVetoReason.PROPOSED_QTY_EXCEEDS_RISK,
                f"Proposed quantity ({proposal.quantity}) exceeds computed risk-safe quantity ({computed_qty})",
                {"proposed_quantity": proposal.quantity, "computed_quantity": computed_qty},
            )

        # 11. Maximum Single Trade Size USD Cap
        trade_nominal_usd = computed_qty * entry
        if trade_nominal_usd > (self.limits.max_single_trade_usd * 1.01):
            return _veto(
                RiskVetoReason.MAX_TRADE_SIZE_EXCEEDED,
                f"Trade nominal size (${trade_nominal_usd:.2f}) exceeds max trade cap (${self.limits.max_single_trade_usd:.2f})",
                {"nominal_usd": trade_nominal_usd, "max_trade_usd": self.limits.max_single_trade_usd},
            )

        # 12. Maximum Daily Spend Cap
        if (daily_orders_placed_usd + trade_nominal_usd) > self.limits.max_daily_spend_usd:
            return _veto(
                RiskVetoReason.DAILY_SPEND_LIMIT_EXCEEDED,
                f"Daily spend (${daily_orders_placed_usd + trade_nominal_usd:.2f}) exceeds limit (${self.limits.max_daily_spend_usd:.2f})",
                {"daily_orders_usd": daily_orders_placed_usd, "proposed_trade_usd": trade_nominal_usd, "limit": self.limits.max_daily_spend_usd},
            )

        # 13. Asset Class Risk Budget & Capital Allocation
        # Total allowed risk capacity across positions = max_risk_per_trade_pct * max_positions
        if instrument.is_crypto:
            max_crypto_risk_usd = account_equity * (self.limits.max_risk_per_trade_pct * self.limits.max_open_positions_crypto) * self.allocation.crypto_budget_pct * 2
            current_crypto_risk = sum(
                self._compute_position_risk_usd(p, prices) for p in positions if self._is_crypto_symbol(p.symbol)
            )
            if (current_crypto_risk + calculated_risk_usd) > max_crypto_risk_usd:
                return _veto(
                    RiskVetoReason.CRYPTO_RISK_BUDGET_EXCEEDED,
                    f"Crypto risk budget exceeded (${current_crypto_risk + calculated_risk_usd:.2f} > max ${max_crypto_risk_usd:.2f})",
                    {"current_risk": current_crypto_risk, "new_risk": calculated_risk_usd, "max_budget": max_crypto_risk_usd},
                )
        else:
            max_forex_risk_usd = account_equity * (self.limits.max_risk_per_trade_pct * self.limits.max_open_positions_forex) * self.allocation.forex_budget_pct * 2
            current_forex_risk = sum(
                self._compute_position_risk_usd(p, prices) for p in positions if not self._is_crypto_symbol(p.symbol)
            )
            if (current_forex_risk + calculated_risk_usd) > max_forex_risk_usd:
                return _veto(
                    RiskVetoReason.FOREX_RISK_BUDGET_EXCEEDED,
                    f"Forex risk budget exceeded (${current_forex_risk + calculated_risk_usd:.2f} > max ${max_forex_risk_usd:.2f})",
                    {"current_risk": current_forex_risk, "new_risk": calculated_risk_usd, "max_budget": max_forex_risk_usd},
                )

        # 14. Crypto Aggregate Exposure Cap
        if instrument.is_crypto:
            current_crypto_exposure = sum(
                p.quantity * p.current_price for p in positions if self._is_crypto_symbol(p.symbol)
            )
            total_crypto_exposure = current_crypto_exposure + trade_nominal_usd
            max_crypto_exposure = account_equity * self.exposure_caps.max_crypto_total_exposure_pct
            if total_crypto_exposure > max_crypto_exposure:
                return _veto(
                    RiskVetoReason.CRYPTO_AGGREGATE_EXPOSURE_CAP_EXCEEDED,
                    f"Total crypto aggregate exposure (${total_crypto_exposure:.2f}) exceeds cap of "
                    f"{self.exposure_caps.max_crypto_total_exposure_pct:.0%} (${max_crypto_exposure:.2f})",
                    {"current_exposure": current_crypto_exposure, "proposed_trade": trade_nominal_usd, "cap": max_crypto_exposure},
                )

        # 15. Net Directional Currency Exposure Caps
        currency_violator = self._check_currency_exposure_caps(
            proposal=proposal,
            instrument=instrument,
            trade_nominal_usd=trade_nominal_usd,
            open_positions=positions,
            current_prices=prices,
            account_equity=account_equity,
        )
        if currency_violator:
            curr, net_usd, cap_usd = currency_violator
            return _veto(
                RiskVetoReason.CURRENCY_EXPOSURE_CAP_EXCEEDED,
                f"Net exposure for currency '{curr}' (${abs(net_usd):.2f}) exceeds {self.exposure_caps.max_net_currency_exposure_pct:.1%} cap (${cap_usd:.2f})",
                {"currency": curr, "net_usd": net_usd, "cap_usd": cap_usd},
            )

        # Approved!
        logger.info(
            f"TRADE APPROVED {symbol} {proposal.action.value}: qty={computed_qty}, risk=${calculated_risk_usd:.2f}, "
            f"nominal=${trade_nominal_usd:.2f}"
        )
        return RiskCheckResult(
            is_approved=True,
            veto_reason=None,
            reason_message=None,
            approved_quantity=computed_qty,
            calculated_risk_usd=calculated_risk_usd,
            details={
                "entry": entry,
                "stop_loss": sl,
                "take_profit": tp,
                "rr": round(rr, 2),
                "nominal_usd": round(trade_nominal_usd, 2),
                "risk_usd": calculated_risk_usd,
            },
        )

    # -------------------------------------------------------------------------
    # Position Stop Modification Checks (Never Widen Stop)
    # -------------------------------------------------------------------------
    def validate_stop_modification(
        self,
        position: Position,
        new_stop: float,
    ) -> tuple[bool, str | None]:
        """Verify that position stop-loss is never widened.
        
        For LONG: new_stop must be >= current stop_loss.
        For SHORT: new_stop must be <= current stop_loss.
        """
        current_sl = position.stop_loss
        if current_sl is None:
            # Setting initial stop is allowed
            return True, None

        if position.side == OrderSide.BUY and new_stop < current_sl:
            msg = f"WIDEN_STOP_FORBIDDEN: Cannot widen LONG stop-loss from {current_sl} down to {new_stop}"
            logger.warning(msg)
            return False, msg
        elif position.side == OrderSide.SELL and new_stop > current_sl:
            msg = f"WIDEN_STOP_FORBIDDEN: Cannot widen SHORT stop-loss from {current_sl} up to {new_stop}"
            logger.warning(msg)
            return False, msg

        return True, None

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _is_crypto_symbol(self, symbol: str) -> bool:
        """Identify if symbol belongs to crypto asset class."""
        inst = self.config.instruments.get_instrument(symbol)
        if inst:
            return inst.is_crypto
        return "/" in symbol or "BTC" in symbol or "ETH" in symbol or "SOL" in symbol

    def _compute_position_risk_usd(self, position: Position, current_prices: Mapping[str, float]) -> float:
        """Estimate open position at-risk dollars based on entry and stop-loss."""
        if position.stop_loss is None:
            return 0.0
        stop_dist = abs(position.entry_price - position.stop_loss)
        inst = self.config.instruments.get_instrument(position.symbol)
        if not inst:
            return position.quantity * stop_dist

        quote_rate = get_quote_to_usd_rate(inst.quote_currency, current_prices)
        return position.quantity * stop_dist * quote_rate

    def _check_currency_exposure_caps(
        self,
        proposal: TradeDecision,
        instrument: InstrumentConfig,
        trade_nominal_usd: float,
        open_positions: Sequence[Position],
        current_prices: Mapping[str, float],
        account_equity: float,
    ) -> tuple[str, float, float] | None:
        """Calculate net exposure for all involved currencies.
        
        Returns:
            (violating_currency, projected_net_usd, allowed_cap_usd) or None if compliant.
        """
        max_currency_exposure_usd = account_equity * self.exposure_caps.max_net_currency_exposure_pct
        net_exposures: dict[str, float] = {}

        # 1. Sum up current open positions exposures
        for pos in open_positions:
            p_inst = self.config.instruments.get_instrument(pos.symbol)
            if not p_inst or p_inst.is_crypto or p_inst.is_gold:
                continue

            base = p_inst.base_currency
            quote = p_inst.quote_currency
            price = current_prices.get(pos.symbol, pos.current_price)
            quote_rate = get_quote_to_usd_rate(quote, current_prices)
            nominal_usd = pos.quantity * price * quote_rate if quote != "USD" else pos.quantity * price

            direction = 1.0 if pos.side == OrderSide.BUY else -1.0
            # Long Base, Short Quote
            net_exposures[base] = net_exposures.get(base, 0.0) + (nominal_usd * direction)
            net_exposures[quote] = net_exposures.get(quote, 0.0) - (nominal_usd * direction)

        # 2. Add proposed trade delta if Forex
        if not instrument.is_crypto and not instrument.is_gold:
            base = instrument.base_currency
            quote = instrument.quote_currency
            direction = 1.0 if proposal.action == ActionType.BUY else -1.0

            net_exposures[base] = net_exposures.get(base, 0.0) + (trade_nominal_usd * direction)
            net_exposures[quote] = net_exposures.get(quote, 0.0) - (trade_nominal_usd * direction)

            for curr, net_val in net_exposures.items():
                if abs(net_val) > max_currency_exposure_usd:
                    return curr, net_val, max_currency_exposure_usd

        return None
