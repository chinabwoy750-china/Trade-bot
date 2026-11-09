"""Comprehensive Unit Tests for Phase 3 Deterministic Risk Management.

Ensures >90% coverage on trading_bot/risk, testing every veto condition,
position sizing logic across Forex, Gold, and Crypto, daily loss limits,
exposure caps, persistent database halts, and stop-loss integrity.
"""

from datetime import datetime, timezone

import pytest

from trading_bot.brokers.models import OrderSide, Position
from trading_bot.config.loader import load_config
from trading_bot.config.models import AppConfig
from trading_bot.decision.models import ActionType, EntryType, TradeDecision
from trading_bot.risk.manager import DeterministicRiskManager
from trading_bot.risk.models import RiskVetoReason
from trading_bot.risk.sizing import PositionSizer, get_quote_to_usd_rate
from trading_bot.storage.database import init_db
from trading_bot.storage.repository import StorageRepository


@pytest.fixture
def test_db_url(tmp_path) -> str:
    db_file = tmp_path / "test_risk.db"
    url = f"sqlite:///{db_file}"
    init_db(url)
    return url


@pytest.fixture
def config(test_db_url) -> AppConfig:
    cfg = load_config()
    cfg.settings.database.url = test_db_url
    return cfg


@pytest.fixture
def repo(test_db_url) -> StorageRepository:
    return StorageRepository(test_db_url)


@pytest.fixture
def risk_manager(config, repo) -> DeterministicRiskManager:
    return DeterministicRiskManager(config=config, repository=repo)


# =============================================================================
# 1. Position Sizing Tests per Instrument Class & Currency Conversions
# =============================================================================

def test_quote_to_usd_rate():
    # Direct USD
    assert get_quote_to_usd_rate("USD") == 1.0

    # Direct quotes with live map
    prices = {"GBP_USD": 1.28, "USD_JPY": 155.0}
    assert get_quote_to_usd_rate("GBP", prices) == 1.28
    assert round(get_quote_to_usd_rate("JPY", prices), 6) == round(1.0 / 155.0, 6)

    # Fallbacks when no live map
    assert get_quote_to_usd_rate("EUR") == 1.08
    assert get_quote_to_usd_rate("JPY") == 1.0 / 150.0


def test_forex_usd_quote_sizing(config):
    # EUR_USD: equity $10,000, 1% risk = $100
    # entry 1.0800, stop 1.0750 -> stop distance 0.0050 (50 pips)
    # risk per unit = 0.0050 * 1.0 = $0.0050
    # units = 100 / 0.0050 = 20,000 units
    inst = config.instruments.get_instrument("EUR_USD")
    assert inst is not None

    qty, risk_usd, err = PositionSizer.calculate_position_size(
        symbol="EUR_USD",
        entry_price=1.0800,
        stop_loss=1.0750,
        equity=10000.0,
        risk_pct=0.01,
        instrument=inst,
    )
    assert err is None
    # Nominal size for 20,000 units is 20,000 * 1.08 = $21,600, which exceeds max_single_trade_usd ($10,000)!
    # Sizer should cap units down to floor(10,000 / 1.08) = 9,259 units!
    assert qty == 9259.0
    assert risk_usd <= 100.0


def test_forex_usd_base_sizing(config):
    # USD_JPY: equity $10,000, 1% risk = $100
    # entry 150.00, stop 149.00 -> stop distance 1.00 JPY
    # conversion rate JPY to USD = 1 / 150.00
    # risk per unit USD = 1.00 / 150.00 = 0.0066667
    # raw units = 100 / (1.00 / 150) = 15,000 units
    inst = config.instruments.get_instrument("USD_JPY")
    assert inst is not None

    qty, risk_usd, err = PositionSizer.calculate_position_size(
        symbol="USD_JPY",
        entry_price=150.00,
        stop_loss=149.00,
        equity=10000.0,
        risk_pct=0.01,
        instrument=inst,
        current_prices={"USD_JPY": 150.00},
    )
    assert err is None
    # Nominal trade cap is $10,000 / 150.0 = capped down
    assert qty > 0
    assert risk_usd <= 100.0


def test_forex_cross_pair_sizing(config):
    # EUR_GBP: quote currency is GBP. GBP_USD = 1.25
    inst = config.instruments.get_instrument("EUR_GBP")
    assert inst is not None

    qty, risk_usd, err = PositionSizer.calculate_position_size(
        symbol="EUR_GBP",
        entry_price=0.8500,
        stop_loss=0.8450,
        equity=10000.0,
        risk_pct=0.01,
        instrument=inst,
        current_prices={"GBP_USD": 1.25},
    )
    assert err is None
    assert qty > 0
    assert risk_usd <= 100.0


def test_gold_sizing(config):
    # XAU_USD: Gold CFD contract size = 1.0 oz
    # Equity $10,000, 1% risk = $100
    # Entry $2650.00, stop $2640.00 -> stop distance $10.00/oz
    # Raw units = 100 / 10 = 10.0 oz
    # Nominal value = 10 * 2650 = $26,500 > max trade USD ($10,000)
    # Capped to floor(10,000 / 2650 * 100) / 100 = 3.77 oz
    inst = config.instruments.get_instrument("XAU_USD")
    assert inst is not None

    qty, risk_usd, err = PositionSizer.calculate_position_size(
        symbol="XAU_USD",
        entry_price=2650.00,
        stop_loss=2640.00,
        equity=10000.0,
        risk_pct=0.01,
        instrument=inst,
    )
    assert err is None
    assert qty == 3.77
    assert risk_usd <= 100.0


def test_crypto_fractional_sizing(config):
    # BTC/USD: Spot crypto
    # Equity $10,000, 1% risk = $100
    # Entry $60,000, stop $58,000 -> stop distance $2,000
    # Raw qty = 100 / 2000 = 0.05 BTC
    # Nominal value = 0.05 * 60,000 = $3,000 <= $10,000 cap
    inst = config.instruments.get_instrument("BTC/USD")
    assert inst is not None

    qty, risk_usd, err = PositionSizer.calculate_position_size(
        symbol="BTC/USD",
        entry_price=60000.0,
        stop_loss=58000.0,
        equity=10000.0,
        risk_pct=0.01,
        instrument=inst,
    )
    assert err is None
    assert qty == 0.05
    assert risk_usd == 100.0


def test_min_order_size_rejection(config):
    # Very small equity $100, 1% risk = $1
    # BTC/USD stop distance $20,000 -> raw qty = 1 / 20000 = 0.00005 BTC < min_order_qty (0.0001)
    inst = config.instruments.get_instrument("BTC/USD")
    assert inst is not None

    qty, risk_usd, err = PositionSizer.calculate_position_size(
        symbol="BTC/USD",
        entry_price=60000.0,
        stop_loss=40000.0,
        equity=100.0,
        risk_pct=0.01,
        instrument=inst,
    )
    assert err is not None
    assert "MIN_ORDER_SIZE_VIOLATION" in err
    assert qty == 0.0


# =============================================================================
# 2. Risk Manager Veto Rules Tests
# =============================================================================

def test_veto_crypto_short(risk_manager):
    # Spot crypto is long-only
    proposal = TradeDecision(
        symbol="BTC/USD",
        action=ActionType.SELL,
        entry_type=EntryType.MARKET,
        stop_loss=61000.0,
        take_profit=58000.0,
        confidence=0.8,
        reasoning="Bearish breakout",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=60000.0,
        current_spread=10.0,
        account_equity=10000.0,
    )
    assert not res.is_approved
    assert res.veto_reason == RiskVetoReason.CRYPTO_SPOT_LONG_ONLY


def test_veto_wrong_side_stop(risk_manager):
    # BUY order with stop ABOVE entry
    proposal = TradeDecision(
        symbol="EUR_USD",
        action=ActionType.BUY,
        entry_type=EntryType.MARKET,
        stop_loss=1.0900,  # Invalid: above 1.0800
        take_profit=1.1000,
        confidence=0.8,
        reasoning="Trend buy",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=1.0800,
        current_spread=0.0001,
        account_equity=10000.0,
    )
    assert not res.is_approved
    assert res.veto_reason == RiskVetoReason.INVALID_STOP_PLACEMENT


def test_veto_min_rr_violation(risk_manager):
    # R:R < 1.5
    proposal = TradeDecision(
        symbol="EUR_USD",
        action=ActionType.BUY,
        entry_type=EntryType.MARKET,
        stop_loss=1.0700,   # stop distance 0.0100 (100 pips)
        take_profit=1.0810, # target distance 0.0010 (10 pips) -> R:R 0.1
        confidence=0.8,
        reasoning="Scalp buy",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=1.0800,
        current_spread=0.0001,
        account_equity=10000.0,
    )
    assert not res.is_approved
    assert res.veto_reason == RiskVetoReason.MIN_RR_VIOLATION


def test_veto_spread_exceeds_stop_ratio(risk_manager):
    # Stop distance 5 pips (0.0005), spread 1.5 pips (0.00015) -> ratio 30% > 20%
    proposal = TradeDecision(
        symbol="EUR_USD",
        action=ActionType.BUY,
        entry_type=EntryType.MARKET,
        stop_loss=1.0795,
        take_profit=1.0820,
        confidence=0.8,
        reasoning="Tight scalp",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=1.0800,
        current_spread=0.00015,
        account_equity=10000.0,
    )
    assert not res.is_approved
    assert res.veto_reason == RiskVetoReason.SPREAD_EXCEEDS_STOP_RATIO


def test_veto_excessive_forex_spread(risk_manager):
    # Major spread > 4.0 pips
    proposal = TradeDecision(
        symbol="EUR_USD",
        action=ActionType.BUY,
        entry_type=EntryType.MARKET,
        stop_loss=1.0700,   # 100 pips
        take_profit=1.1000,
        confidence=0.8,
        reasoning="Normal trade",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=1.0800,
        current_spread=0.0005,  # 5.0 pips > 4.0 pips
        account_equity=10000.0,
    )
    assert not res.is_approved
    assert res.veto_reason == RiskVetoReason.EXCESSIVE_FOREX_SPREAD


def test_veto_excessive_crypto_spread(risk_manager):
    # Crypto spread > 0.3%
    proposal = TradeDecision(
        symbol="BTC/USD",
        action=ActionType.BUY,
        entry_type=EntryType.MARKET,
        stop_loss=58000.0,
        take_profit=64000.0,
        confidence=0.8,
        reasoning="Breakout",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=60000.0,
        current_spread=300.0,  # 300 / 60000 = 0.5% > 0.3%
        account_equity=10000.0,
    )
    assert not res.is_approved
    assert res.veto_reason == RiskVetoReason.EXCESSIVE_CRYPTO_SPREAD


def test_veto_averaging_down(risk_manager):
    # Existing BUY position at 1.0850. New BUY proposal at 1.0800 (lower price -> averaging down!)
    existing_pos = Position(
        id="pos_1",
        symbol="EUR_USD",
        side=OrderSide.BUY,
        quantity=5000.0,
        entry_price=1.0850,
        current_price=1.0800,
        stop_loss=1.0750,
    )
    proposal = TradeDecision(
        symbol="EUR_USD",
        action=ActionType.BUY,
        entry_type=EntryType.MARKET,
        stop_loss=1.0750,
        take_profit=1.0900,
        confidence=0.8,
        reasoning="Add to loser",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=1.0800,
        current_spread=0.0001,
        account_equity=10000.0,
        open_positions=[existing_pos],
    )
    assert not res.is_approved
    assert res.veto_reason == RiskVetoReason.AVERAGING_DOWN_FORBIDDEN


def test_veto_widening_stop(risk_manager):
    # Test validate_stop_modification directly
    pos_long = Position(
        id="pos_l",
        symbol="EUR_USD",
        side=OrderSide.BUY,
        quantity=1000.0,
        entry_price=1.0800,
        current_price=1.0820,
        stop_loss=1.0750,
    )
    # Moving long stop DOWN is widening -> VETO!
    ok, msg = risk_manager.validate_stop_modification(pos_long, new_stop=1.0740)
    assert not ok
    assert "WIDEN_STOP_FORBIDDEN" in msg

    # Moving long stop UP is trailing/tightening -> ALLOWED
    ok, msg = risk_manager.validate_stop_modification(pos_long, new_stop=1.0780)
    assert ok
    assert msg is None

    # For SHORT position:
    pos_short = Position(
        id="pos_s",
        symbol="EUR_USD",
        side=OrderSide.SELL,
        quantity=1000.0,
        entry_price=1.0800,
        current_price=1.0780,
        stop_loss=1.0850,
    )
    # Moving short stop UP is widening -> VETO!
    ok, msg = risk_manager.validate_stop_modification(pos_short, new_stop=1.0860)
    assert not ok
    assert "WIDEN_STOP_FORBIDDEN" in msg

    # Moving short stop DOWN is tightening -> ALLOWED
    ok, msg = risk_manager.validate_stop_modification(pos_short, new_stop=1.0820)
    assert ok


def test_veto_max_open_positions(risk_manager):
    # Max open positions is 6
    positions = [
        Position(id=f"pos_{i}", symbol="EUR_USD", side=OrderSide.BUY, quantity=1000.0, entry_price=1.08, current_price=1.08)
        for i in range(6)
    ]
    proposal = TradeDecision(
        symbol="GBP_USD",
        action=ActionType.BUY,
        entry_type=EntryType.MARKET,
        stop_loss=1.2400,
        take_profit=1.2800,
        confidence=0.8,
        reasoning="Setup",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=1.2500,
        current_spread=0.0001,
        account_equity=10000.0,
        open_positions=positions,
    )
    assert not res.is_approved
    assert res.veto_reason == RiskVetoReason.MAX_TOTAL_POSITIONS


def test_veto_crypto_aggregate_exposure_cap(risk_manager):
    # Max crypto aggregate exposure is 20% of equity ($2,000 on $10,000 equity)
    # Existing BTC position of $1,800
    pos_btc = Position(
        id="btc_pos",
        symbol="BTC/USD",
        side=OrderSide.BUY,
        quantity=0.03,
        entry_price=60000.0,
        current_price=60000.0,
        stop_loss=58000.0,
    )
    # New ETH proposal of $500 nominal -> total $2,300 > $2,000 cap!
    proposal = TradeDecision(
        symbol="ETH/USD",
        action=ActionType.BUY,
        entry_type=EntryType.MARKET,
        stop_loss=2400.0,
        take_profit=2800.0,
        confidence=0.8,
        reasoning="Eth breakout",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=2500.0,
        current_spread=0.5,
        account_equity=10000.0,
        open_positions=[pos_btc],
    )
    assert not res.is_approved
    assert res.veto_reason == RiskVetoReason.CRYPTO_AGGREGATE_EXPOSURE_CAP_EXCEEDED


def test_veto_daily_spend_limit(risk_manager):
    # Max daily spend is $50,000.
    proposal = TradeDecision(
        symbol="EUR_USD",
        action=ActionType.BUY,
        entry_type=EntryType.MARKET,
        stop_loss=1.0750,
        take_profit=1.0900,
        confidence=0.8,
        reasoning="Trend buy",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=1.0800,
        current_spread=0.0001,
        account_equity=10000.0,
        daily_orders_placed_usd=48000.0,  # Trade nominal ~$10,000 -> 48k + 10k > 50k!
    )
    assert not res.is_approved
    assert res.veto_reason == RiskVetoReason.DAILY_SPEND_LIMIT_EXCEEDED


def test_veto_proposed_qty_exceeds_risk(risk_manager):
    # Proposed quantity is manually set to 50,000 units when calculated risk-safe qty is 9,259
    proposal = TradeDecision(
        symbol="EUR_USD",
        action=ActionType.BUY,
        quantity=50000.0,
        entry_type=EntryType.MARKET,
        stop_loss=1.0750,
        take_profit=1.0900,
        confidence=0.8,
        reasoning="Oversized trade",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=1.0800,
        current_spread=0.0001,
        account_equity=10000.0,
    )
    assert not res.is_approved
    assert res.veto_reason == RiskVetoReason.PROPOSED_QTY_EXCEEDS_RISK


# =============================================================================
# 3. Persistent Safety Halts, Killswitch, and Daily Loss Boundary
# =============================================================================

def test_killswitch_persistence(risk_manager, repo, config):
    # Activate killswitch
    risk_manager.activate_killswitch(reason="Testing emergency halt")

    # Verify is_system_halted is True
    is_halted, msg, reason = risk_manager.is_system_halted()
    assert is_halted
    assert reason == RiskVetoReason.KILLSWITCH_ACTIVE

    # Create a BRAND NEW manager instance pointing to the same repo (simulate bot restart)
    new_manager = DeterministicRiskManager(config=config, repository=repo)
    is_halted_restarted, _, reason_restarted = new_manager.is_system_halted()
    assert is_halted_restarted
    assert reason_restarted == RiskVetoReason.KILLSWITCH_ACTIVE

    # Deactivate killswitch via manual command
    new_manager.deactivate_killswitch()
    is_halted_after, _, _ = new_manager.is_system_halted()
    assert not is_halted_after


def test_consecutive_loss_persistent_halt(risk_manager, repo, config):
    # Record 3 losses -> should not halt yet (limit is 4)
    for _ in range(3):
        risk_manager.record_trade_result(is_win=False)
    assert not risk_manager.is_system_halted()[0]

    # 4th loss -> triggers persistent halt
    risk_manager.record_trade_result(is_win=False)
    is_halted, msg, reason = risk_manager.is_system_halted()
    assert is_halted
    assert reason == RiskVetoReason.CONSECUTIVE_LOSS_HALT

    # Trade proposal must now be vetoed
    proposal = TradeDecision(
        symbol="EUR_USD",
        action=ActionType.BUY,
        entry_type=EntryType.MARKET,
        stop_loss=1.0750,
        take_profit=1.0900,
        confidence=0.8,
        reasoning="Valid setup",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=1.0800,
        current_spread=0.0001,
        account_equity=10000.0,
    )
    assert not res.is_approved
    assert res.veto_reason == RiskVetoReason.CONSECUTIVE_LOSS_HALT

    # Operator reset
    risk_manager.reset_halt()
    assert not risk_manager.is_system_halted()[0]


def test_global_daily_loss_halt(risk_manager, repo):
    # Starting equity was initialized at $10,000 at UTC 00:00
    now_utc = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
    repo.get_or_create_daily_performance(starting_equity=10000.0, date_str="2026-11-09")

    # Current equity drops to $9,650 (3.5% loss > 3% daily limit)
    tripped, msg = risk_manager.check_daily_loss_halt(current_equity=9650.0, now_utc=now_utc)
    assert tripped
    assert "GLOBAL_DAILY_LOSS_HALT" in msg

    # Persistent state should be set
    is_halted, _, reason = risk_manager.is_system_halted()
    assert is_halted
    assert reason == RiskVetoReason.GLOBAL_DAILY_LOSS_HALT


def test_veto_logged_to_audit_table(risk_manager, repo):
    risk_manager.reset_halt()
    proposal = TradeDecision(
        symbol="BTC/USD",
        action=ActionType.SELL,  # Vetoed: spot crypto is long-only
        entry_type=EntryType.MARKET,
        stop_loss=61000.0,
        take_profit=58000.0,
        confidence=0.8,
        reasoning="Audit check",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=60000.0,
        current_spread=10.0,
        account_equity=10000.0,
    )
    assert not res.is_approved

    # Check audit record in DB
    vetoes = repo.get_recent_vetoes(limit=1)
    assert len(vetoes) == 1
    assert vetoes[0]["rule_name"] == RiskVetoReason.CRYPTO_SPOT_LONG_ONLY.value
    assert vetoes[0]["symbol"] == "BTC/USD"
    assert vetoes[0]["proposed_action"] == "SELL"


# =============================================================================
# 4. Approved Trades & Full Execution Flows
# =============================================================================

def test_approved_forex_buy(risk_manager):
    # Compliant Forex BUY trade with account equity $500,000 (3% currency cap = $15,000)
    risk_manager.reset_halt()
    proposal = TradeDecision(
        symbol="EUR_USD",
        action=ActionType.BUY,
        entry_type=EntryType.MARKET,
        stop_loss=1.0750,
        take_profit=1.0900,  # stop: 50 pips, target: 100 pips -> R:R 2.0 >= 1.5
        confidence=0.85,
        reasoning="Bullish trend structure",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=1.0800,
        current_spread=0.0001,  # 1 pip spread
        account_equity=500000.0,
    )
    assert res.is_approved
    assert res.approved_quantity > 0
    assert res.calculated_risk_usd > 0
    assert res.veto_reason is None


def test_approved_forex_sell(risk_manager):
    # Compliant Forex SELL trade with account equity $500,000
    risk_manager.reset_halt()
    proposal = TradeDecision(
        symbol="EUR_USD",
        action=ActionType.SELL,
        entry_type=EntryType.MARKET,
        stop_loss=1.0850,
        take_profit=1.0700,  # stop: 50 pips, target: 100 pips -> R:R 2.0 >= 1.5
        confidence=0.9,
        reasoning="Bearish breakdown structure",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=1.0800,
        current_spread=0.0001,
        account_equity=500000.0,
    )
    assert res.is_approved
    assert res.approved_quantity > 0
    assert res.calculated_risk_usd > 0


def test_approved_crypto_buy(risk_manager):
    # Compliant Crypto BUY trade with $100,000 equity (20% crypto cap = $20,000)
    risk_manager.reset_halt()
    proposal = TradeDecision(
        symbol="BTC/USD",
        action=ActionType.BUY,
        quantity=0.1666,
        entry_type=EntryType.MARKET,
        stop_loss=58000.0,
        take_profit=64000.0,  # risk 2000, reward 4000 -> R:R 2.0
        confidence=0.85,
        reasoning="Consolidation breakout above resistance",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=60000.0,
        current_spread=20.0,  # 20 / 60000 = 0.033% < 0.3%
        account_equity=100000.0,
    )
    assert res.is_approved
    assert res.approved_quantity > 0


def test_approved_gold_buy(risk_manager):
    risk_manager.reset_halt()
    proposal = TradeDecision(
        symbol="XAU_USD",
        action=ActionType.BUY,
        entry_type=EntryType.MARKET,
        stop_loss=2640.0,
        take_profit=2670.0,  # risk 10, reward 20 -> R:R 2.0
        confidence=0.8,
        reasoning="Gold continuation",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=2650.0,
        current_spread=0.20,
        account_equity=10000.0,
    )
    assert res.is_approved
    assert res.approved_quantity > 0


# =============================================================================
# 5. Additional Edge-Cases & Branch Coverage
# =============================================================================

def test_veto_unknown_instrument(risk_manager):
    risk_manager.reset_halt()
    proposal = TradeDecision(
        symbol="UNKNOWN_XYZ_COIN",
        action=ActionType.BUY,
        entry_type=EntryType.MARKET,
        stop_loss=10.0,
        take_profit=25.0,
        confidence=0.8,
        reasoning="Test unknown symbol",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=15.0,
        current_spread=0.1,
        account_equity=10000.0,
    )
    assert not res.is_approved
    assert res.veto_reason == RiskVetoReason.MIN_ORDER_SIZE_VIOLATION


def test_veto_sell_wrong_side_stop(risk_manager):
    # SELL order where stop_loss is below entry (should be above)
    risk_manager.reset_halt()
    proposal = TradeDecision(
        symbol="EUR_USD",
        action=ActionType.SELL,
        entry_type=EntryType.MARKET,
        stop_loss=1.0750,  # Invalid: below 1.0800 for SELL!
        take_profit=1.0700,
        confidence=0.8,
        reasoning="Wrong side stop for sell",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=1.0800,
        current_spread=0.0001,
        account_equity=10000.0,
    )
    assert not res.is_approved
    assert res.veto_reason == RiskVetoReason.INVALID_STOP_PLACEMENT


def test_veto_sell_wrong_side_tp(risk_manager):
    # SELL order where take_profit is above entry (should be below)
    risk_manager.reset_halt()
    proposal = TradeDecision(
        symbol="EUR_USD",
        action=ActionType.SELL,
        entry_type=EntryType.MARKET,
        stop_loss=1.0850,
        take_profit=1.0900,  # Invalid: above 1.0800 for SELL!
        confidence=0.8,
        reasoning="Wrong side target for sell",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=1.0800,
        current_spread=0.0001,
        account_equity=10000.0,
    )
    assert not res.is_approved
    assert res.veto_reason == RiskVetoReason.MIN_RR_VIOLATION


def test_veto_averaging_down_sell(risk_manager):
    # Existing SHORT position at 1.0800. Proposing another SHORT at 1.0850 (higher price -> averaging down on short!)
    risk_manager.reset_halt()
    existing_short = Position(
        id="pos_s1",
        symbol="EUR_USD",
        side=OrderSide.SELL,
        quantity=5000.0,
        entry_price=1.0800,
        current_price=1.0850,
        stop_loss=1.0900,
    )
    proposal = TradeDecision(
        symbol="EUR_USD",
        action=ActionType.SELL,
        entry_type=EntryType.MARKET,
        stop_loss=1.0900,
        take_profit=1.0700,
        confidence=0.8,
        reasoning="Average down on short",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=1.0850,
        current_spread=0.0001,
        account_equity=10000.0,
        open_positions=[existing_short],
    )
    assert not res.is_approved
    assert res.veto_reason == RiskVetoReason.AVERAGING_DOWN_FORBIDDEN


def test_veto_max_forex_positions(risk_manager):
    risk_manager.reset_halt()
    # 4 open forex positions (limit is 4)
    positions = [
        Position(id=f"fx_{i}", symbol=s, side=OrderSide.BUY, quantity=1000.0, entry_price=1.0, current_price=1.0, stop_loss=0.99)
        for i, s in enumerate(["EUR_USD", "GBP_USD", "USD_JPY", "USD_CHF"])
    ]
    proposal = TradeDecision(
        symbol="AUD_USD",
        action=ActionType.BUY,
        entry_type=EntryType.MARKET,
        stop_loss=0.6400,
        take_profit=0.6800,
        confidence=0.8,
        reasoning="5th forex position",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=0.6500,
        current_spread=0.0001,
        account_equity=10000.0,
        open_positions=positions,
    )
    assert not res.is_approved
    assert res.veto_reason == RiskVetoReason.MAX_FOREX_POSITIONS


def test_veto_max_crypto_positions(risk_manager):
    risk_manager.reset_halt()
    # 3 open crypto positions (limit is 3)
    positions = [
        Position(id=f"cr_{i}", symbol=s, side=OrderSide.BUY, quantity=0.01, entry_price=100.0, current_price=100.0, stop_loss=90.0)
        for i, s in enumerate(["BTC/USD", "ETH/USD", "SOL/USD"])
    ]
    proposal = TradeDecision(
        symbol="XRP/USD",
        action=ActionType.BUY,
        entry_type=EntryType.MARKET,
        stop_loss=0.45,
        take_profit=0.65,
        confidence=0.8,
        reasoning="4th crypto position",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=0.50,
        current_spread=0.0005,
        account_equity=10000.0,
        open_positions=positions,
    )
    assert not res.is_approved
    assert res.veto_reason == RiskVetoReason.MAX_CRYPTO_POSITIONS


def test_veto_forex_risk_budget_exceeded(risk_manager):
    risk_manager.reset_halt()
    # Open positions already using up full risk budget
    # Equity $10,000 -> max_risk_per_trade 1% ($100), max forex positions 4 -> forex budget 50%
    # max_forex_risk_usd = 10000 * (0.01 * 4) * 0.5 * 2 = $400
    pos1 = Position(id="p1", symbol="EUR_USD", side=OrderSide.BUY, quantity=20000.0, entry_price=1.0800, current_price=1.0800, stop_loss=1.0600)  # risk = 20000 * 0.02 = $400
    proposal = TradeDecision(
        symbol="GBP_USD",
        action=ActionType.BUY,
        entry_type=EntryType.MARKET,
        stop_loss=1.2400,
        take_profit=1.2800,
        confidence=0.8,
        reasoning="Risk budget exceed",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=1.2500,
        current_spread=0.0001,
        account_equity=10000.0,
        open_positions=[pos1],
    )
    assert not res.is_approved
    assert res.veto_reason == RiskVetoReason.FOREX_RISK_BUDGET_EXCEEDED


def test_veto_currency_exposure_cap(risk_manager):
    risk_manager.reset_halt()
    # Currency cap: 3% of equity ($300 on $10,000 equity)
    # Existing EUR position with $280 nominal
    pos_eur = Position(
        id="p_eur",
        symbol="EUR_USD",
        side=OrderSide.BUY,
        quantity=250.0,
        entry_price=1.0800,
        current_price=1.0800,
        stop_loss=1.0700,
    )
    # Proposal for EUR_GBP that adds another $150 EUR exposure -> total $420 > $300 cap!
    proposal = TradeDecision(
        symbol="EUR_GBP",
        action=ActionType.BUY,
        entry_type=EntryType.MARKET,
        stop_loss=0.8400,
        take_profit=0.8700,
        confidence=0.8,
        reasoning="EUR exposure test",
    )
    res = risk_manager.validate_trade(
        proposal=proposal,
        current_price=0.8500,
        current_spread=0.0001,
        account_equity=10000.0,
        open_positions=[pos_eur],
        current_prices={"EUR_USD": 1.08, "EUR_GBP": 0.85, "GBP_USD": 1.25},
    )
    assert not res.is_approved
    assert res.veto_reason == RiskVetoReason.CURRENCY_EXPOSURE_CAP_EXCEEDED


def test_sizing_input_validations(config):
    inst_eur = config.instruments.get_instrument("EUR_USD")

    # Non-positive equity
    qty, risk, err = PositionSizer.calculate_position_size("EUR_USD", 1.08, 1.07, 0.0, 0.01, inst_eur)
    assert err == "EQUITY_NON_POSITIVE"

    # Zero stop distance
    qty, risk, err = PositionSizer.calculate_position_size("EUR_USD", 1.08, 1.08, 10000.0, 0.01, inst_eur)
    assert err == "ZERO_STOP_DISTANCE"

    # Convenience wrapper
    from trading_bot.risk.sizing import calculate_position_size
    q, r, e = calculate_position_size("EUR_USD", 1.08, 1.0750, 10000.0, 0.01, inst_eur)
    assert e is None
    assert q > 0


def test_validate_stop_modification_no_existing_stop(risk_manager):
    # If position has no existing stop loss, setting one is always allowed
    pos = Position(
        id="pos_no_sl",
        symbol="EUR_USD",
        side=OrderSide.BUY,
        quantity=1000.0,
        entry_price=1.0800,
        current_price=1.0820,
        stop_loss=None,
    )
    ok, err = risk_manager.validate_stop_modification(pos, new_stop=1.0750)
    assert ok is True
    assert err is None
