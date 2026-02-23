import time
import logging
from datetime import datetime
from app.services.trade_orchestrator import run_entry_engine
from app.services.mstock_trade_monitor import monitor_trades

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


# -----------------------------------------
# Market Time Check (Optional but Recommended)
# -----------------------------------------
def is_market_open():
    now = datetime.now().time()

    market_start = datetime.strptime("09:15", "%H:%M").time()
    market_end = datetime.strptime("23:59", "%H:%M").time()

    return market_start <= now <= market_end


# -----------------------------------------
# Main Scheduler Loop
# -----------------------------------------
def run_scheduler():

    logger.info("🚀 Trading Engine Started")

    while True:

        try:

            if is_market_open():

                logger.info("Running Entry Engine...")
                run_entry_engine()

                logger.info("Running Exit Monitor...")
                monitor_trades()

            else:
                logger.info("Market closed. Sleeping...")

        except Exception as e:
            logger.error("Scheduler Error: %s", str(e))

        # Run every 60 seconds
        time.sleep(60)


# -----------------------------------------
# ENTRY POINT
# -----------------------------------------
if __name__ == "__main__":
    run_scheduler()
