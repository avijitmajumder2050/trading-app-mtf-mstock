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
# Daily backtest Feb-Nov 2026: max 2 open gave the best win rate
# and smallest drawdown; position sizing uses half the cash each.
# --------------------------------------------------
ENTRY_WEEKDAYS = (0, 1, 2, 3, 4)  # Monday-Friday
ENTRY_CUTOFF = time(11, 25)
MAX_OPEN_TRADES = 2               # None = no limit; funds are the only cap


def open_and_today_stocks():
    """(stocks with an open trade, stocks entered or exited today)."""
    df = load_trades()

    if df.empty or "status" not in df.columns:
        return [], []

    open_stocks = df.loc[df["status"] != "CLOSED", "stock_name"].tolist()

    today = datetime.now().date()
    touched_today = pd.Series(False, index=df.index)
    for col in ("entry_date", "closed_at"):
        if col in df.columns:
            touched_today |= pd.to_datetime(df[col], format="mixed", errors="coerce").dt.date == today
    today_stocks = df.loc[touched_today, "stock_name"].tolist()

    return open_stocks, today_stocks


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

    open_stocks, today_stocks = open_and_today_stocks()
    slots = float("inf") if MAX_OPEN_TRADES is None else MAX_OPEN_TRADES - len(open_stocks)

    if slots <= 0:
        logger.info("Open-trade limit reached (%d/%d). Skipping entry engine.", len(open_stocks), MAX_OPEN_TRADES)
        return

    logger.info("Running selection engine (%s slot(s) left)...", slots)

    # 1️⃣ Stock selection (skip stocks held, or bought/sold today)
    ranked = select_weekly_breakouts(exclude=set(open_stocks) | set(today_stocks))

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
