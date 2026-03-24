import pandas as pd
import logging
from datetime import datetime, time
from app.services.mstock_trade_store import load_trades, save_trades
from app.services.mstock_order_executor import place_order_with_logging, cancel_order
from app.services.mstock_telegram_sender import mstock_send_telegram_message
from app.services.mstock_order_executor import place_order_with_logging
from app.services.mstock_live import get_mstock_ltp
logger = logging.getLogger(__name__)

MARKET_CLOSE = time(15, 30)  # NSE close

def monitor_trades():
    df = load_trades()
    if df.empty:
        return
    # --------------------------------
    # 1️⃣ Build Symbol List (Batch LTP)
    # --------------------------------
    active_df = df[df["status"] != "CLOSED"]

    if active_df.empty:
        return

    stock_list = active_df["stock_name"].dropna().unique().tolist()
    symbols = [f"NSE:{name}" for name in stock_list]

    live_data = get_mstock_ltp(symbols)

    if not live_data:
        logger.warning("LTP API returned empty data. Skipping cycle.")
        return
    updated_trades = []
    now = datetime.now()
    is_market_close = now.time() >= MARKET_CLOSE

    for _, trade in df.iterrows():

        if trade["status"] == "CLOSED":
            updated_trades.append(trade)
            continue

        stock = trade["stock_name"]
        symbol = f"NSE:{stock}"

        ltp_data = live_data.get(symbol)
        if not ltp_data:
            logger.warning("LTP missing for %s", stock)
            updated_trades.append(trade)
            continue
        ltp = float(ltp_data.get("last_price", 0))
        if ltp == 0:
            logger.warning("Invalid LTP for %s", stock)
            updated_trades.append(trade)
            continue
        # ------------------------------
        # Day-SL check
        # ------------------------------
        if trade.get("sl_hit_today"):
            if is_market_close:
                exit_payload = {
                    "_variety": "REGULAR",
                    "_tradingsymbol": stock,
                    "_exchange": "NSE",
                    "_transaction_type": "SELL",
                    "_order_type": "MARKET",
                    "_quantity": trade["remaining_qty"],
                    "_product": "MTF",
                    "_validity": "DAY",
                    "_price": 0,
                    "_trigger_price": 0,
                    "_disclosed_quantity": 0,
                    "_tag": "DAY_SL_EXIT"
                }
                place_order_with_logging(exit_payload)
                trade["status"] = "CLOSED"
                trade["exit_reason"] = "SL_DAY_EXIT"
                trade["remaining_qty"] = 0
                trade["closed_at"] = datetime.now()
                trade["sl_hit_today"] = False
                logger.info("%s exited at day close due to SL.", stock)
            else:
                
                logger.info("%s SL triggered today, waiting for day end")
                updated_trades.append(trade)
                continue

        # ------------------------------
        # SL trigger detection
        # ------------------------------
        elif trade.get("current_sl") and ltp <= trade["current_sl"] and not trade.get("sl_hit_today"):
            trade["sl_hit_today"] = True
            message = (
        f"🔴 <b>SL TRIGGERED</b>\n\n"
        f"<b>Stock:</b> {stock}\n"
        f"<b>LTP:</b> {ltp}\n"
        f"<b>SL:</b> {trade['current_sl']}\n"
        f"<b>Remaining Qty:</b> {trade['remaining_qty']}"
    )

            mstock_send_telegram_message(message)
            logger.info("%s SL triggered today at LTP %.2f", stock, ltp)

        # ------------------------------
        # T1 partial booking
        # ------------------------------
        if not trade.get("t1_hit") and ltp >= trade["target1"]:
            partial_qty = max(1, trade["remaining_qty"] // 2)
            exit_payload = {
                "_variety": "REGULAR",
                "_tradingsymbol": stock,
                "_exchange": "NSE",
                "_transaction_type": "SELL",
                "_order_type": "MARKET",
                "_quantity": partial_qty,
                "_product": "MTF",
                "_validity": "DAY",
                "_price": 0,
                "_trigger_price": 0,
                "_disclosed_quantity": 0,
                "_tag": "T1_PARTIAL"
            }
            place_order_with_logging(exit_payload)
            trade["remaining_qty"] -= partial_qty
            trade["t1_hit"] = True
            trade["current_sl"] = trade["entry_price"]  # move SL to breakeven

            message = (
    f"🟢 <b>T1 HIT - PARTIAL BOOKED</b>\n\n"
    f"<b>Stock:</b> {stock}\n"
    f"<b>LTP:</b> {ltp}\n"
    f"<b>Booked Qty:</b> {partial_qty}\n"
    f"<b>Remaining Qty:</b> {trade['remaining_qty']}\n"
    f"<b>SL moved to:</b> {trade['entry_price']}"
)

            mstock_send_telegram_message(message)

            logger.info("%s T1 hit at %.2f", stock, ltp)

            

        # ------------------------------
        # T2 full exit
        # ------------------------------
        
        if (
            trade["status"] != "CLOSED"
            and trade["remaining_qty"] > 0
            and ltp >= trade["target2"]
            ):

            exit_payload = {
                "_variety": "REGULAR",
                "_tradingsymbol": stock,
                "_exchange": "NSE",
                "_transaction_type": "SELL",
                "_order_type": "MARKET",
                "_quantity": trade["remaining_qty"],
                "_product": "MTF",
                "_validity": "DAY",
                "_price": 0,
                "_trigger_price": 0,
                "_disclosed_quantity": 0,
                "_tag": "T2_EXIT"
            }
            place_order_with_logging(exit_payload)
            message = (
    f"🎯 <b>T2 TARGET HIT</b>\n\n"
    f"<b>Stock:</b> {stock}\n"
    f"<b>LTP:</b> {ltp}\n"
    f"<b>Exit Qty:</b> {trade['remaining_qty']}\n"
    f"<b>Trade Closed</b>"
)

            mstock_send_telegram_message(message)

            logger.info("%s T2 hit. Trade closed.", stock)

            trade["status"] = "CLOSED"
            trade["exit_reason"] = "T2"
            trade["remaining_qty"] = 0
            trade["closed_at"] = datetime.now()

        updated_trades.append(trade)

    save_trades(pd.DataFrame(updated_trades))
