import logging
from datetime import datetime, time
import pandas as pd

from app.services.selection_engine import select_weekly_breakouts
from app.services.rule_engine import enrich_with_trade_rules
from app.services.mstock_order_executor import execute_mtf_entry
from app.services.mstock_trade_store import load_trades
from app.services.mstock_telegram_sender import mstock_send_telegram_message

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --------------------------------------------------
# WEEKLY MODE: enter Mon/Tue only, max 2 trades a week,
# hold until Friday exit (see mstock_trade_monitor)
# --------------------------------------------------
ENTRY_WEEKDAYS = (0, 1)          # Monday, Tuesday
ENTRY_CUTOFF = time(11, 25)
MAX_TRADES_PER_WEEK = 2


def stocks_traded_this_week():
    df = load_trades()

    if df.empty or "entry_date" not in df.columns:
        return []

    entry_dates = pd.to_datetime(df["entry_date"], format="mixed", errors="coerce").dt.date
    today = datetime.now().date()
    week_start = today - pd.Timedelta(days=today.weekday())

    week = df[(entry_dates >= week_start) & (entry_dates <= today)]
    return week["stock_name"].tolist()


# --------------------------------------------------
# ENTRY ENGINE
# --------------------------------------------------
def run_entry_engine():

    now = datetime.now()

    if now.weekday() not in ENTRY_WEEKDAYS:
        logger.info("Weekly mode: entries only on Mon/Tue. Skipping entry engine.")
        return

    if now.time() > ENTRY_CUTOFF:
        logger.info("Entry cutoff %s passed. Skipping entry engine.", ENTRY_CUTOFF)
        return

    traded = stocks_traded_this_week()
    slots = MAX_TRADES_PER_WEEK - len(traded)

    if slots <= 0:
        logger.info("Weekly limit reached (%d/%d). Skipping entry engine.", len(traded), MAX_TRADES_PER_WEEK)
        return

    logger.info("Running weekly selection engine (%d slot(s) left)...", slots)

    # 1️⃣ Stock selection (one trade per stock per week)
    ranked = select_weekly_breakouts(exclude=traded)

    if not ranked:
        logger.info("No weekly breakout yet. Skipping cycle.")
        return

    # 2️⃣ Apply trade rules (position size)
    trades = enrich_with_trade_rules(
        ranked,
        max_loss_per_trade=1000
    )

    if not trades:
        logger.info("No valid trades after rule engine.")
        return

    # 3️⃣ Enter best candidates until the weekly slots are filled
    for trade in trades:

        if slots <= 0:
            break

        stock_name = trade["stock_name"]

        logger.info("Attempting entry for %s", stock_name)

        result = execute_mtf_entry(trade)

        if result:
            slots -= 1

            telegram_message = (
                f"🚀 <b>WEEKLY ENTRY EXECUTED</b>\n\n"
                f"<b>Stock:</b> {stock_name}\n"
                f"<b>Qty:</b> {trade.get('qty')}\n"
                f"<b>Entry:</b> {trade.get('entry_price')}\n"
                f"<b>SL:</b> {trade.get('sl')}\n"
                f"<b>Exit:</b> SL (day close) or Friday 15:15\n"
                f"<b>Order ID:</b> {result['entry_order_id']}"
            )

            mstock_send_telegram_message(telegram_message)

            logger.info(
                "Entry SUCCESS for %s | Order ID: %s",
                stock_name,
                result["entry_order_id"]
            )

        else:
            logger.warning(
                "Entry FAILED for %s. Trying next ranked stock...",
                stock_name
            )
