"""Pydantic v2 models for system, instrument, and risk configuration."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SystemSettings(BaseModel):
    """System runtime parameters."""
    app_name: str = "AI Multi-Asset Trading Bot"
    version: str = "1.0.0"
    mode: Literal["demo", "backtest", "live"] = "demo"
    cycle_interval_minutes: int = Field(default=15, ge=1, le=1440)
    position_monitor_interval_seconds: int = Field(default=60, ge=5, le=3600)
    max_data_age_seconds: int = Field(default=300, ge=10, le=3600)
    timezone: str = "UTC"


class ForexSessionSettings(BaseModel):
    """Forex weekend session boundary times."""
    close_day_of_week: int = Field(default=4, ge=0, le=6)  # 4 = Friday
    close_hour_utc: int = Field(default=21, ge=0, le=23)
    close_minute_utc: int = Field(default=0, ge=0, le=59)
    reopen_day_of_week: int = Field(default=6, ge=0, le=6)  # 6 = Sunday
    reopen_hour_utc: int = Field(default=21, ge=0, le=23)
    reopen_minute_utc: int = Field(default=0, ge=0, le=59)


class DecisionAgentSettings(BaseModel):
    """LLM decision agent parameters."""
    provider: Literal["gemini", "anthropic"] = "gemini"
    model: str = "gemini-2.5-flash"
    temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    timeout_seconds: int = Field(default=20, ge=2, le=120)
    max_retries: int = Field(default=2, ge=0, le=5)
    consecutive_hold_diagnostic_threshold: int = Field(default=4, ge=2, le=20)


class EconomicCalendarSettings(BaseModel):
    """Macro and economic calendar parameters."""
    blackout_before_minutes: int = Field(default=30, ge=0, le=120)
    blackout_after_minutes: int = Field(default=30, ge=0, le=120)
    min_impact_level: Literal["LOW", "MEDIUM", "HIGH"] = "HIGH"


class LoggingSettings(BaseModel):
    """Logging destination and format settings."""
    level: str = "INFO"
    log_dir: str = "logs"
    rotation_max_bytes: int = Field(default=10485760, ge=1024)
    backup_count: int = Field(default=5, ge=1)
    json_format: bool = True
    console_output: bool = True


class DatabaseSettings(BaseModel):
    """Storage parameters."""
    url: str = "sqlite:///trading_bot.db"


class SettingsConfig(BaseModel):
    """Composite system settings from settings.yaml."""
    system: SystemSettings = Field(default_factory=SystemSettings)
    forex_session: ForexSessionSettings = Field(default_factory=ForexSessionSettings)
    decision_agent: DecisionAgentSettings = Field(default_factory=DecisionAgentSettings)
    economic_calendar: EconomicCalendarSettings = Field(default_factory=EconomicCalendarSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)


class InstrumentConfig(BaseModel):
    """Instrument metadata for Forex, Gold, or Crypto."""
    symbol: str
    display_name: str
    base_currency: str
    quote_currency: str
    pip_size: float | None = None
    contract_size: float = 1.0
    min_order_units: float | None = None
    min_order_qty: float | None = None
    broker: Literal["oanda", "alpaca"] = "oanda"

    @property
    def is_crypto(self) -> bool:
        return self.broker == "alpaca"

    @property
    def is_forex(self) -> bool:
        return self.broker == "oanda" and self.base_currency != "XAU"

    @property
    def is_gold(self) -> bool:
        return self.base_currency == "XAU"


class InstrumentsConfig(BaseModel):
    """List of all configured tradable instruments."""
    forex: list[InstrumentConfig] = Field(default_factory=list)
    crypto: list[InstrumentConfig] = Field(default_factory=list)

    def get_instrument(self, symbol: str) -> InstrumentConfig | None:
        """Find instrument configuration by standard symbol."""
        for inst in self.forex + self.crypto:
            if inst.symbol == symbol:
                return inst
        return None

    @property
    def all_instruments(self) -> list[InstrumentConfig]:
        return self.forex + self.crypto


class RiskLimits(BaseModel):
    """Trade sizing and position limits."""
    max_risk_per_trade_pct: float = Field(default=0.01, gt=0.0, le=0.05)
    min_risk_per_trade_pct: float = Field(default=0.002, gt=0.0, le=0.05)
    max_open_positions_total: int = Field(default=6, ge=1, le=50)
    max_open_positions_forex: int = Field(default=4, ge=1, le=50)
    max_open_positions_crypto: int = Field(default=3, ge=1, le=50)
    min_risk_reward_ratio: float = Field(default=1.5, ge=1.0)
    max_single_trade_usd: float = Field(default=10000.0, gt=0.0)
    max_daily_spend_usd: float = Field(default=50000.0, gt=0.0)

    @field_validator("min_risk_per_trade_pct")
    @classmethod
    def validate_min_less_than_max(cls, v: float, info) -> float:
        max_val = info.data.get("max_risk_per_trade_pct", 0.01)
        if v > max_val:
            raise ValueError(f"min_risk_per_trade_pct ({v}) cannot exceed max_risk_per_trade_pct ({max_val})")
        return v


class CapitalAllocation(BaseModel):
    """Forex vs Crypto capital split."""
    forex_budget_pct: float = Field(default=0.50, ge=0.0, le=1.0)
    crypto_budget_pct: float = Field(default=0.50, ge=0.0, le=1.0)

    @field_validator("crypto_budget_pct")
    @classmethod
    def validate_budget_sum(cls, v: float, info) -> float:
        forex = info.data.get("forex_budget_pct", 0.50)
        if round(forex + v, 4) != 1.0:
            raise ValueError(f"forex_budget_pct ({forex}) + crypto_budget_pct ({v}) must sum to 1.0")
        return v


class CurrencyExposureCaps(BaseModel):
    """Single currency and asset class limits."""
    max_net_currency_exposure_pct: float = Field(default=0.03, gt=0.0, le=0.20)
    max_crypto_total_exposure_pct: float = Field(default=0.20, gt=0.0, le=1.0)


class SafetyHalts(BaseModel):
    """Loss limits and emergency halts."""
    global_daily_loss_limit_pct: float = Field(default=0.03, gt=0.0, le=0.20)
    max_consecutive_losses: int = Field(default=4, ge=1, le=20)
    killswitch_active: bool = False


class SpreadAndSlippage(BaseModel):
    """Spread filters."""
    max_spread_to_stop_ratio: float = Field(default=0.20, gt=0.0, le=1.0)
    max_forex_spread_pips: float = Field(default=4.0, gt=0.0)
    max_crypto_spread_pct: float = Field(default=0.003, gt=0.0)


class RiskConfig(BaseModel):
    """Complete risk parameters from risk.yaml."""
    limits: RiskLimits = Field(default_factory=RiskLimits)
    capital_allocation: CapitalAllocation = Field(default_factory=CapitalAllocation)
    currency_exposure_caps: CurrencyExposureCaps = Field(default_factory=CurrencyExposureCaps)
    safety_halts: SafetyHalts = Field(default_factory=SafetyHalts)
    spread_and_slippage: SpreadAndSlippage = Field(default_factory=SpreadAndSlippage)


class AppConfig(BaseModel):
    """Unified application configuration."""
    settings: SettingsConfig
    instruments: InstrumentsConfig
    risk: RiskConfig
