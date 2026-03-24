import time
import logging
import asyncio
from datetime import datetime, time as dt_time
from app.services.trade_orchestrator import run_entry_engine
from app.services.mstock_trade_monitor import monitor_trades
from app.bot.scheduler import terminate_after_delay   # adjust path if needed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)

ENTRY_START = dt_time(9, 31)
ENTRY_END = dt_time(11, 0)
EVENING_TIME = dt_time(16, 0)


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
