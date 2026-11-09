import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select

from trading_bot.decision.models import DecisionResult, HoldDecision, TradeDecision
from trading_bot.storage.database import get_session
from trading_bot.storage.models import (
    DailyPerformanceRecord,
    DecisionRecord,
    RiskVetoRecord,
    SystemStateRecord,
)


class StorageRepository:
    """High-level repository for SQLite/Postgres persistence."""

    def __init__(self, db_url: str = "sqlite:///trading_bot.db") -> None:
        self.db_url = db_url

    def save_decision(
        self,
        decision: DecisionResult,
        cycle_id: str | None = None,
        analyst_inputs: dict[str, Any] | None = None,
        raw_ai_output: str | None = None,
        was_vetoed: bool = False,
        veto_reason: str | None = None,
    ) -> DecisionRecord:
        """Persist every decision (BUY, SELL, HOLD) along with thesis and inputs."""
        inputs_json = json.dumps(analyst_inputs) if analyst_inputs else None

        with get_session(self.db_url) as session:
            if isinstance(decision, TradeDecision):
                record = DecisionRecord(
                    cycle_id=cycle_id,
                    symbol=decision.symbol,
                    action=decision.action.value,
                    quantity=decision.quantity,
                    entry_type=decision.entry_type.value,
                    limit_price=decision.limit_price,
                    stop_loss=decision.stop_loss,
                    take_profit=decision.take_profit,
                    risk_reward=decision.risk_reward,
                    risk_usd=decision.risk_usd,
                    confidence=decision.confidence,
                    reasoning=decision.reasoning,
                    invalidation_condition=decision.invalidation_condition,
                    analyst_inputs_json=inputs_json,
                    raw_ai_output=raw_ai_output,
                    was_vetoed=was_vetoed,
                    veto_reason=veto_reason,
                )
            elif isinstance(decision, HoldDecision):
                record = DecisionRecord(
                    cycle_id=cycle_id,
                    symbol=decision.symbol,
                    action=decision.action.value,
                    reason_code=decision.reason_code.value,
                    reasoning=decision.reasoning,
                    analyst_inputs_json=inputs_json,
                    raw_ai_output=raw_ai_output,
                    was_vetoed=was_vetoed,
                    veto_reason=veto_reason,
                )
            else:
                raise TypeError(f"Unknown decision type: {type(decision)}")

            session.add(record)
            session.flush()
            session.refresh(record)
            return record

    def save_risk_veto(
        self,
        rule_name: str,
        symbol: str,
        proposed_action: str,
        reason: str,
        details: dict[str, Any] | None = None,
    ) -> RiskVetoRecord:
        """Log a deterministic risk veto."""
        details_json = json.dumps(details) if details else None
        with get_session(self.db_url) as session:
            record = RiskVetoRecord(
                rule_name=rule_name,
                symbol=symbol,
                proposed_action=proposed_action,
                reason=reason,
                details_json=details_json,
            )
            session.add(record)
            session.flush()
            session.refresh(record)
            return record

    def get_recent_decisions(self, limit: int = 50) -> list[dict[str, Any]]:
        """Fetch recent decisions ordered by timestamp descending."""
        with get_session(self.db_url) as session:
            stmt = select(DecisionRecord).order_by(desc(DecisionRecord.created_at)).limit(limit)
            records = session.scalars(stmt).all()
            return [
                {
                    "id": r.id,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "cycle_id": r.cycle_id,
                    "symbol": r.symbol,
                    "action": r.action,
                    "reason_code": r.reason_code,
                    "quantity": r.quantity,
                    "entry_type": r.entry_type,
                    "limit_price": r.limit_price,
                    "stop_loss": r.stop_loss,
                    "take_profit": r.take_profit,
                    "risk_reward": r.risk_reward,
                    "risk_usd": r.risk_usd,
                    "confidence": r.confidence,
                    "reasoning": r.reasoning,
                    "invalidation_condition": r.invalidation_condition,
                    "was_vetoed": r.was_vetoed,
                    "veto_reason": r.veto_reason,
                }
                for r in records
            ]

    def get_recent_vetoes(self, limit: int = 50) -> list[dict[str, Any]]:
        """Fetch recent risk vetoes."""
        with get_session(self.db_url) as session:
            stmt = select(RiskVetoRecord).order_by(desc(RiskVetoRecord.created_at)).limit(limit)
            records = session.scalars(stmt).all()
            return [
                {
                    "id": r.id,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "rule_name": r.rule_name,
                    "symbol": r.symbol,
                    "proposed_action": r.proposed_action,
                    "reason": r.reason,
                    "details": json.loads(str(r.details_json)) if r.details_json else {},
                }
                for r in records
            ]

    def get_or_create_daily_performance(
        self,
        starting_equity: float,
        date_str: str | None = None,
    ) -> DailyPerformanceRecord:
        """Get or initialize today's daily performance tracking record."""
        today = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with get_session(self.db_url) as session:
            stmt = select(DailyPerformanceRecord).where(DailyPerformanceRecord.date_str == today)
            record = session.scalars(stmt).first()
            if record is None:
                record = DailyPerformanceRecord(
                    date_str=today,
                    starting_equity=starting_equity,
                    current_equity=starting_equity,
                    realized_pnl=0.0,
                    unrealized_pnl=0.0,
                    total_trades=0,
                    win_trades=0,
                    loss_trades=0,
                    consecutive_losses=0,
                    is_halted=False,
                )
                session.add(record)
                session.flush()
                session.refresh(record)
            return record

    def get_or_create_system_state(self, state_key: str = "default_state") -> SystemStateRecord:
        """Fetch or initialize persistent guardrail state across bot restarts."""
        with get_session(self.db_url) as session:
            stmt = select(SystemStateRecord).where(SystemStateRecord.state_key == state_key)
            record = session.scalars(stmt).first()
            if record is None:
                record = SystemStateRecord(
                    state_key=state_key,
                    is_halted=False,
                    halt_reason=None,
                    killswitch_active=False,
                    consecutive_losses=0,
                )
                session.add(record)
                session.flush()
                session.refresh(record)
            return record

    def set_system_halt(self, reason: str, state_key: str = "default_state") -> None:
        """Persist emergency or daily loss halt."""
        with get_session(self.db_url) as session:
            stmt = select(SystemStateRecord).where(SystemStateRecord.state_key == state_key)
            record = session.scalars(stmt).first()
            if record is None:
                record = SystemStateRecord(state_key=state_key)
                session.add(record)
            record.is_halted = True
            record.halt_reason = reason
            record.halted_at = datetime.now(timezone.utc)

    def clear_system_halt(self, state_key: str = "default_state") -> None:
        """Clear persistent halt state via explicit manual action."""
        with get_session(self.db_url) as session:
            stmt = select(SystemStateRecord).where(SystemStateRecord.state_key == state_key)
            record = session.scalars(stmt).first()
            if record:
                record.is_halted = False
                record.halt_reason = None
                record.halted_at = None
                record.consecutive_losses = 0

    def set_killswitch(self, active: bool, state_key: str = "default_state") -> None:
        """Set persistent emergency killswitch state."""
        with get_session(self.db_url) as session:
            stmt = select(SystemStateRecord).where(SystemStateRecord.state_key == state_key)
            record = session.scalars(stmt).first()
            if record is None:
                record = SystemStateRecord(state_key=state_key)
                session.add(record)
            record.killswitch_active = active
            if active:
                record.is_halted = True
                record.halt_reason = "MANUAL_KILLSWITCH_TRIGGERED"
                record.halted_at = datetime.now(timezone.utc)
            else:
                record.is_halted = False
                record.halt_reason = None
                record.halted_at = None

    def record_trade_outcome(self, is_win: bool, state_key: str = "default_state") -> int:
        """Update consecutive loss count in persistent storage.
        
        Returns:
            Current consecutive loss count.
        """
        with get_session(self.db_url) as session:
            stmt = select(SystemStateRecord).where(SystemStateRecord.state_key == state_key)
            record = session.scalars(stmt).first()
            if record is None:
                record = SystemStateRecord(state_key=state_key)
                session.add(record)

            if is_win:
                record.consecutive_losses = 0
            else:
                record.consecutive_losses += 1
            return record.consecutive_losses

