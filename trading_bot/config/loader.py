"""Configuration loader with YAML parsing and environment variable injection."""

import os
from pathlib import Path
from typing import Any

import yaml

from trading_bot.config.models import (
    AppConfig,
    InstrumentsConfig,
    RiskConfig,
    SettingsConfig,
)
from trading_bot.core.mode import ModeGate


def load_yaml(file_path: Path | str) -> dict[str, Any]:
    """Safely read and parse a YAML file."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path.resolve()}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
        return data or {}


def load_app_config(config_dir: str | Path = "config") -> AppConfig:
    """Load, merge, and validate all application configurations.
    
    Args:
        config_dir: Directory containing settings.yaml, instruments.yaml, risk.yaml
        
    Returns:
        Validated AppConfig instance.
    """
    base_path = Path(config_dir)
    settings_data = load_yaml(base_path / "settings.yaml")
    instruments_data = load_yaml(base_path / "instruments.yaml")
    risk_data = load_yaml(base_path / "risk.yaml")

    # Inject environment variables into settings if present
    env_mode = os.getenv("MODE")
    if env_mode:
        if "system" not in settings_data:
            settings_data["system"] = {}
        settings_data["system"]["mode"] = env_mode

    env_db = os.getenv("DATABASE_URL")
    if env_db:
        if "database" not in settings_data:
            settings_data["database"] = {}
        settings_data["database"]["url"] = env_db

    env_log_level = os.getenv("LOG_LEVEL")
    if env_log_level:
        if "logging" not in settings_data:
            settings_data["logging"] = {}
        settings_data["logging"]["level"] = env_log_level

    # Parse through Pydantic schemas
    settings_cfg = SettingsConfig.model_validate(settings_data)
    instruments_cfg = InstrumentsConfig.model_validate(instruments_data)
    risk_cfg = RiskConfig.model_validate(risk_data)

    # Validate mode safety gate
    ModeGate.validate_safety()

    return AppConfig(
        settings=settings_cfg,
        instruments=instruments_cfg,
        risk=risk_cfg,
    )


# Singleton cache
_cached_config: AppConfig | None = None


def get_config(reload: bool = False, config_dir: str | Path = "config") -> AppConfig:
    """Return cached AppConfig or load anew."""
    global _cached_config
    if _cached_config is None or reload:
        _cached_config = load_app_config(config_dir)
    return _cached_config


# Backward-compatible alias
load_config = load_app_config
