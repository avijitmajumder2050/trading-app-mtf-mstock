import logging
from datetime import datetime
import pandas as pd

from app.services.selection_engine import select_and_rank_stocks
from app.services.rule_engine import enrich_with_trade_rules
from app.services.mstock_order_executor import execute_mtf_entry
from app.services.mstock_trade_store import load_trades
from app.services.mstock_telegram_sender import mstock_send_telegram_message

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# --------------------------------------------------
# GLOBAL DAILY LOCK
# --------------------------------------------------
def already_traded_today():
    df = load_trades()

    if df.empty:
        return False

    today = datetime.now().strftime("%Y-%m-%d")

    if "entry_date" not in df.columns:
        return False

    today_trades = df[
        (df["entry_date"].astype(str) == today)
    ]

    return not today_trades.empty


# --------------------------------------------------
# ENTRY ENGINE - ONE TRADE PER DAY
# --------------------------------------------------
def run_entry_engine():

    # 🔒 DAILY TRADE LOCK
    if already_traded_today():
        logger.info("Trade already taken today. Skipping entry engine.")

        # Optional: send telegram when skipped
        # mstock_send_telegram_message(
        #     "⚠️ Trade already taken today. Entry engine skipped."
        # )

        return

    logger.info("Running selection engine...")

    # 1️⃣ Stock selection
    ranked = select_and_rank_stocks(interval="5minute")

    if not ranked or len(ranked) < 1:
        logger.info("Less than 1 breakout stocks found. Skipping cycle.")
        return

    # 2️⃣ Apply trade rules
    trades = enrich_with_trade_rules(
        ranked,
        max_loss_per_trade=1000
    )

    if not trades:
        logger.info("No valid trades after rule engine.")
        return

    # 3️⃣ Try ranked stocks until one succeeds
    for trade in trades:

        stock_name = trade["stock_name"]

        logger.info("Attempting entry for %s", stock_name)

        result = execute_mtf_entry(trade)

        if result:

            entry_price = trade.get("entry_price")
            sl = trade.get("sl")
            target1 = trade.get("target1")
            target2 = trade.get("target2")
            qty = trade.get("qty")

            telegram_message = (
                f"🚀 <b>MTF ENTRY EXECUTED</b>\n\n"
                f"<b>Stock:</b> {stock_name}\n"
                f"<b>Qty:</b> {qty}\n"
                f"<b>Entry:</b> {entry_price}\n"
                f"<b>SL:</b> {sl}\n"
                f"<b>T1:</b> {target1}\n"
                f"<b>T2:</b> {target2}\n"
                f"<b>Order ID:</b> {result['entry_order_id']}"
            )

            # ✅ Send Telegram Alert
            mstock_send_telegram_message(telegram_message)

            logger.info(
                "Entry SUCCESS for %s | Order ID: %s",
                stock_name,
                result["entry_order_id"]
            )

            break

        else:
            logger.warning(
                "Entry FAILED for %s. Trying next ranked stock...",
                stock_name
            )

    else:
        logger.info("No entries executed in this cycle.")
