#!/usr/bin/env python3
"""Run bot in DEMO / paper trading mode."""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import os
from trading_bot.config.loader import load_app_config
from trading_bot.core.logger import get_logger, setup_logging
from trading_bot.core.mode import ModeGate
from trading_bot.storage.database import init_db

# Enforce demo mode
os.environ["MODE"] = "demo"

setup_logging(level="INFO")
logger = get_logger("demo_runner")


def main() -> None:
    mode = ModeGate.validate_safety()
    logger.info("Initializing trading bot in %s mode...", mode.value.upper())
    config = load_app_config()
    init_db(config.settings.database.url)
    logger.info(
        "Phase 1 Foundation ready. Scheduled cycles (15m interval) will engage upon Phase 2-6 completion."
    )
    print("\n[OK] Demo environment verified. Ready for Phase 2 Data Layer integration.")


if __name__ == "__main__":
    main()
