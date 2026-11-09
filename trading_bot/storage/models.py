from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 declarative base class."""



def utc_now_dt() -> datetime:
    return datetime.now(timezone.utc)


class DecisionRecord(Base):
    """Audit table storing EVERY decision (BUY, SELL, HOLD)."""
    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=utc_now_dt, index=True, nullable=False)
    cycle_id = Column(String(64), index=True, nullable=True)
    symbol = Column(String(32), index=True, nullable=True)
    action = Column(String(16), nullable=False)  # BUY | SELL | HOLD
    reason_code = Column(String(32), nullable=True)  # NO_EDGE, etc.
    quantity = Column(Float, nullable=True)
    entry_type = Column(String(16), nullable=True)
    limit_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    risk_reward = Column(Float, nullable=True)
    risk_usd = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    reasoning = Column(Text, nullable=False)
    invalidation_condition = Column(Text, nullable=True)
    analyst_inputs_json = Column(Text, nullable=True)  # Serialized analyst team findings
    raw_ai_output = Column(Text, nullable=True)        # Exact unmodified LLM text response
    was_vetoed = Column(Boolean, default=False, nullable=False)
    veto_reason = Column(Text, nullable=True)


class RiskVetoRecord(Base):
    """Audit table logging every veto exercised by the deterministic risk manager."""
    __tablename__ = "risk_vetoes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=utc_now_dt, index=True, nullable=False)
    rule_name = Column(String(64), index=True, nullable=False)
    symbol = Column(String(32), index=True, nullable=False)
    proposed_action = Column(String(16), nullable=False)
    reason = Column(Text, nullable=False)
    details_json = Column(Text, nullable=True)


class OrderRecord(Base):
    """Audit table for all placed and executed broker orders."""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=utc_now_dt, index=True, nullable=False)
    client_order_id = Column(String(64), unique=True, index=True, nullable=False)
    broker_order_id = Column(String(64), index=True, nullable=True)
    broker = Column(String(32), nullable=False)
    symbol = Column(String(32), index=True, nullable=False)
    side = Column(String(16), nullable=False)
    order_type = Column(String(16), nullable=False)
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    status = Column(String(32), nullable=False)
    filled_quantity = Column(Float, default=0.0)
    avg_fill_price = Column(Float, nullable=True)
    updated_at = Column(DateTime, default=utc_now_dt, onupdate=utc_now_dt)


class PositionRecord(Base):
    """Table tracking lifetime of open and closed positions."""
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    position_id = Column(String(64), unique=True, index=True, nullable=False)
    symbol = Column(String(32), index=True, nullable=False)
    side = Column(String(16), nullable=False)
    quantity = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=False)
    unrealized_pnl = Column(Float, default=0.0)
    realized_pnl = Column(Float, default=0.0)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    status = Column(String(16), default="OPEN", index=True)  # OPEN | CLOSED
    opened_at = Column(DateTime, default=utc_now_dt, nullable=False)
    closed_at = Column(DateTime, nullable=True)


class DailyPerformanceRecord(Base):
    """Daily track record for calculating daily drawdowns and consecutive loss limits."""
    __tablename__ = "daily_performance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date_str = Column(String(10), unique=True, index=True, nullable=False)  # YYYY-MM-DD
    starting_equity = Column(Float, nullable=False)
    current_equity = Column(Float, nullable=False)
    realized_pnl = Column(Float, default=0.0)
    unrealized_pnl = Column(Float, default=0.0)
    total_trades = Column(Integer, default=0)
    win_trades = Column(Integer, default=0)
    loss_trades = Column(Integer, default=0)
    consecutive_losses = Column(Integer, default=0)
    is_halted = Column(Boolean, default=False)
    halt_reason = Column(String(128), nullable=True)
    updated_at = Column(DateTime, default=utc_now_dt, onupdate=utc_now_dt)


class SystemStateRecord(Base):
    """Persistent system guardrail state across restarts (killswitch, halts, consecutive losses)."""
    __tablename__ = "system_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    state_key = Column(String(32), unique=True, index=True, default="default_state", nullable=False)
    is_halted = Column(Boolean, default=False, nullable=False)
    halt_reason = Column(String(256), nullable=True)
    killswitch_active = Column(Boolean, default=False, nullable=False)
    consecutive_losses = Column(Integer, default=0, nullable=False)
    halted_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=utc_now_dt, onupdate=utc_now_dt, nullable=False)

