import time
import logging
import asyncio
from datetime import datetime

# Configure logging before importing any app modules — several of them log at
# import time, and logging.basicConfig() is a no-op once handlers exist.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    force=True,
)

from app.services.trade_orchestrator import run_entry_engine
from app.services.mstock_trade_monitor import monitor_trades
from app.bot.scheduler import terminate_after_delay   # adjust path if needed
from app.config.settings import ENTRY_START, ENTRY_END, EVENING_TIME

logger = logging.getLogger(__name__)


async def main():

    now = datetime.now().time()

    # ==============================
    # MORNING SESSION (9:31–11:00)
    # ==============================
    if ENTRY_START <= now <= ENTRY_END:

        logger.info("Morning trading session started")

        while datetime.now().time() <= ENTRY_END:

            try:
                logger.info("Running Entry Engine...")
                run_entry_engine()

                logger.info("Running Monitor...")
                monitor_trades()

            except Exception as e:
                logger.error("Error: %s", str(e))

            time.sleep(60)

        logger.info("11:00 reached. Scheduling EC2 termination (2–5 min delay)...")
        await terminate_after_delay(5)

    # ==============================
    # EVENING SESSION (4 PM Run Once)
    # ==============================
    elif now >= EVENING_TIME:

        logger.info("4 PM Monitor run started")

        try:
            monitor_trades()
        except Exception as e:
            logger.error("Error: %s", str(e))

        logger.info("Evening monitor complete. Scheduling EC2 termination...")
        await terminate_after_delay(5)

    else:
        logger.info("Outside trading window. Nothing to run.")


if __name__ == "__main__":
    asyncio.run(main())
