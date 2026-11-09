#!/usr/bin/env python3
"""System healthcheck script for Docker, systemd, and cron monitoring."""

from pathlib import Path
import sys

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from trading_bot.config.loader import load_app_config
from trading_bot.core.mode import ModeGate
from trading_bot.storage.database import init_db, get_session
from sqlalchemy import text


def run_healthcheck() -> int:
    """Validate system configuration, storage access, and safety gates."""
    print("==================================================")
    print("       AI MULTI-ASSET TRADING BOT HEALTHCHECK     ")
    print("==================================================")
    
    try:
        # 1. Mode check
        mode = ModeGate.validate_safety()
        print(f"[OK] Operational Mode: {mode.value.upper()}")
        if mode.value == "live":
            print(" [!] CAUTION: Live mode is ACTIVE.")
        else:
            print(" [i] Safe Mode (demo/paper) active.")
            
        # 2. Config check
        config = load_app_config()
        print(f"[OK] Configuration Loaded: {config.settings.system.app_name} v{config.settings.system.version}")
        print(f"     - Tradable Forex & Gold Pairs: {len(config.instruments.forex)}")
        print(f"     - Tradable Crypto Spot Coins: {len(config.instruments.crypto)}")
        print(f"     - Risk Per Trade: {config.risk.limits.max_risk_per_trade_pct * 100:.1f}%")
        print(f"     - Global Daily Loss Halt: {config.risk.safety_halts.global_daily_loss_limit_pct * 100:.1f}%")

        # 3. Database check
        init_db(config.settings.database.url)
        with get_session(config.settings.database.url) as session:
            session.execute(text("SELECT 1"))
        print(f"[OK] SQLite Database Connected: {config.settings.database.url}")

        print("--------------------------------------------------")
        print("[SUCCESS] All Phase 1 healthchecks PASSED.")
        print("==================================================")
        return 0
    except Exception as err:
        print(f"[FAIL] Healthcheck failed: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run_healthcheck())
