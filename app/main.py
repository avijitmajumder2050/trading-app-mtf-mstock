import time
import logging
import asyncio
from datetime import datetime, time as dt_time

# Configure logging before importing any app modules — several of them log at
# import time, and logging.basicConfig() is a no-op once handlers exist.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    force=True,
)

from app.services.trade_orchestrator import run_entry_engine
from app.services.mstock_trade_monitor import (
    monitor_trades, exit_life_cycle, life_exit_due_today, LIFE_EXIT_TIME, LIFE_TRADING_DAYS,
)
from app.services.mstock_reconcile import reconcile_positions
from app.bot.scheduler import terminate_after_delay   # adjust path if needed
from app.config.settings import ENTRY_START, ENTRY_END, EVENING_TIME

logger = logging.getLogger(__name__)

POLL_SECONDS = 30  # 1m sustain check needs frequent polls


LAST_EXIT_ATTEMPT = dt_time(15, 28)


def session_end(exit_due):
    # A trade reaching its last day: stay up until its exit is done (before 15:30 close)
    if exit_due:
        return max(ENTRY_END, LAST_EXIT_ATTEMPT)
    return ENTRY_END


async def main():

    now = datetime.now().time()

    # ==============================
    # MARKET SESSION (ENTRY_START–ENTRY_END; until LIFE_EXIT_TIME exit
    # on days a trade reaches its last day)
    # ==============================
    exit_due = life_exit_due_today()

    if ENTRY_START <= now <= session_end(exit_due):

        logger.info("Morning trading session started (day-%d exit due today: %s)", LIFE_TRADING_DAYS, exit_due)

        while datetime.now().time() <= session_end(exit_due):

            try:
                logger.info("Running Entry Engine...")
                run_entry_engine()

                logger.info("Running Monitor...")
                monitor_trades()

                if exit_due and datetime.now().time() >= LIFE_EXIT_TIME:
                    logger.info("%s: day-%d exit of due trades", LIFE_EXIT_TIME, LIFE_TRADING_DAYS)
                    remaining = exit_life_cycle()
                    # retry failed sells until just before the 15:30 close
                    if remaining == 0 or datetime.now().time() >= LAST_EXIT_ATTEMPT:
                        break

            except Exception as e:
                logger.error("Error: %s", str(e))

            time.sleep(POLL_SECONDS)

        # Morning only: by now last evening's SL-exit AMOs have filled at open
        reconcile_positions()

        logger.info("Session end reached. Scheduling EC2 termination (1–5 min delay)...")
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
