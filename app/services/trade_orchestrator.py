import logging
from datetime import datetime, time
import pandas as pd

from app.services.selection_engine import select_weekly_breakouts
from app.services.rule_engine import enrich_with_trade_rules
from app.services.mstock_order_executor import execute_mtf_entry
from app.services.mstock_trade_store import load_trades
from app.services.mstock_telegram_sender import mstock_send_telegram_message
from app.broker.fund_manager import get_mstock_cached_fund

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --------------------------------------------------
# 5-DAY MODE: enter any weekday, hold each trade 5 trading days
# (entry day = day 1) or until SL — see mstock_trade_monitor.
# Up to MAX_TRADES_PER_WEEK entries per Mon-Sun week, on one day or
# spread over several; several qualifying stocks can be entered in the
# same cycle while slots remain. A stock can be bought again only after
# its previous trade has closed. Position sizing uses half the cash each.
# --------------------------------------------------
ENTRY_WEEKDAYS = (0, 1, 2, 3, 4)  # Monday-Friday
ENTRY_CUTOFF = time(11, 25)
MAX_TRADES_PER_WEEK = 3           # None = no weekly limit; funds are the only cap


def open_stocks_and_week_entries():
    """(stocks with an open trade, number of entries this Mon-Sun week)."""
    df = load_trades()

    if df.empty or "status" not in df.columns:
        return [], 0

    open_stocks = df.loc[df["status"] != "CLOSED", "stock_name"].tolist()

    if "entry_date" not in df.columns:
        return open_stocks, 0

    entry_dates = pd.to_datetime(df["entry_date"], format="mixed", errors="coerce").dt.date
    today = datetime.now().date()
    week_start = today - pd.Timedelta(days=today.weekday())
    week_entries = int(((entry_dates >= week_start) & (entry_dates <= today)).sum())

    return open_stocks, week_entries


# --------------------------------------------------
# ENTRY ENGINE
# --------------------------------------------------
def run_entry_engine():

    now = datetime.now()

    if now.weekday() not in ENTRY_WEEKDAYS:
        logger.info("No entries on weekends. Skipping entry engine.")
        return

    if now.time() > ENTRY_CUTOFF:
        logger.info("Entry cutoff %s passed. Skipping entry engine.", ENTRY_CUTOFF)
        return

    open_stocks, week_entries = open_stocks_and_week_entries()
    slots = float("inf") if MAX_TRADES_PER_WEEK is None else MAX_TRADES_PER_WEEK - week_entries

    if slots <= 0:
        logger.info("Weekly limit reached (%d/%d). Skipping entry engine.", week_entries, MAX_TRADES_PER_WEEK)
        return

    logger.info("Running selection engine (%s weekly slot(s) left)...", slots)

    # 1️⃣ Stock selection (a stock still held is not bought again)
    ranked = select_weekly_breakouts(exclude=set(open_stocks))

    if not ranked:
        logger.info("No weekly breakout yet. Skipping cycle.")
        return

    # 2️⃣ Enter best candidates; size each one from a fresh fund balance
    #     so earlier buys in this cycle are accounted for
    for stock in ranked:

        if slots <= 0:
            break

        get_mstock_cached_fund(refresh=True)
        sized = enrich_with_trade_rules([stock], max_loss_per_trade=1000)

        if not sized:
            logger.info("%s skipped after rule engine (invalid SL or not enough funds).", stock["stock_name"])
            continue

        trade = sized[0]
        stock_name = trade["stock_name"]

        logger.info("Attempting entry for %s", stock_name)

        result = execute_mtf_entry(trade)

        if result:
            slots -= 1

            telegram_message = (
                f"🚀 <b>ENTRY EXECUTED</b>\n\n"
                f"<b>Stock:</b> {stock_name}\n"
                f"<b>Qty:</b> {trade.get('qty')}\n"
                f"<b>Entry:</b> {trade.get('entry_price')}\n"
                f"<b>SL:</b> {trade.get('sl')}\n"
                f"<b>Exit:</b> SL (day close) or day-5 15:15\n"
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
