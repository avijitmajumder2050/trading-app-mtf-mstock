import pandas as pd
import logging
from datetime import datetime, time
from app.services.mstock_trade_store import load_trades, save_trades
from app.services.mstock_order_executor import place_order_confirmed, get_order_fill, DEAD_STATUSES
from app.services.mstock_telegram_sender import mstock_send_telegram_message
from app.services.mstock_live import get_mstock_ltp
logger = logging.getLogger(__name__)

MARKET_CLOSE = time(15, 30)  # NSE close


def _as_bool(value):
    # CSV round-trips can turn booleans into "True"/"False" strings or NaN
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value) and not pd.isna(value)


def _sell(stock, qty, tag):
    payload = {
        "_variety": "REGULAR",
        "_tradingsymbol": f"{stock}-EQ",
        "_exchange": "NSE",
        "_transaction_type": "SELL",
        "_order_type": "MARKET",
        "_quantity": int(qty),
        "_product": "MTF",
        "_validity": "DAY",
        "_price": 0,
        "_trigger_price": 0,
        "_disclosed_quantity": 0,
        "_tag": tag
    }
    result = place_order_confirmed(payload)
    if not result:
        mstock_send_telegram_message(
            f"⚠️ <b>EXIT ORDER FAILED</b>\n\n"
            f"<b>Stock:</b> {stock}\n"
            f"<b>Qty:</b> {qty}\n"
            f"<b>Tag:</b> {tag}\n"
            f"Trade left open, will retry next cycle."
        )
    return result


def _close(trade, reason, result, ltp):
    trade["exit_qty"] = trade["remaining_qty"]
    trade["status"] = "CLOSED"
    trade["exit_reason"] = reason
    trade["remaining_qty"] = 0
    trade["exit_order_id"] = result["order_id"]
    # AMO placed after close fills at next open: price unknown until verified
    trade["exit_price"] = result["avg_price"] if not result["pending"] else None
    trade["exit_pending"] = result["pending"]
    trade["closed_at"] = datetime.now()
    trade["sl_hit_today"] = False


def verify_pending_exits(df):
    """
    Evening SL exits are AMOs that fill at the next open. Confirm they
    filled; if the broker rejected/cancelled one, reopen the trade so the
    position is not left unmanaged.
    """
    if "exit_pending" not in df.columns:
        return False

    changed = False
    for idx in df.index[df["exit_pending"].map(_as_bool)]:
        trade = df.loc[idx]
        stock = trade["stock_name"]
        fill = get_order_fill(trade["exit_order_id"], wait_seconds=0)
        if not fill:
            continue

        if fill["filled_qty"] > 0:
            df.loc[idx, "exit_price"] = fill["avg_price"]
            df.loc[idx, "exit_pending"] = False
            changed = True
            logger.info("%s pending exit filled @ %.2f", stock, fill["avg_price"])

        elif fill["status"] in DEAD_STATUSES:
            df.loc[idx, "status"] = "ACTIVE"
            df.loc[idx, "exit_reason"] = ""
            df.loc[idx, "remaining_qty"] = int(trade["exit_qty"])
            df.loc[idx, "sl_hit_today"] = True  # exit again at next close
            df.loc[idx, "exit_pending"] = False
            changed = True
            mstock_send_telegram_message(
                f"⚠️ <b>SL EXIT NOT FILLED</b>\n\n"
                f"<b>Stock:</b> {stock}\n"
                f"<b>Qty:</b> {int(trade['exit_qty'])}\n"
                f"<b>Broker:</b> {fill['status']} - {fill['message']}\n"
                f"Trade reopened, exit retried at next close."
            )
            logger.error("%s pending exit %s -> reopened", stock, fill["status"])

    return changed


def monitor_trades():
    df = load_trades()
    if df.empty:
        return

    if verify_pending_exits(df):
        save_trades(df)

    # --------------------------------
    # 1️⃣ Build Symbol List (Batch LTP)
    # --------------------------------
    active_df = df[df["status"] != "CLOSED"]

    if active_df.empty:
        return

    stock_list = active_df["stock_name"].dropna().unique().tolist()
    symbols = [f"NSE:{name}-EQ" for name in stock_list]

    live_data = get_mstock_ltp(symbols)

    if not live_data:
        logger.warning("LTP API returned empty data. Skipping cycle.")
        return
    updated_trades = []
    is_market_close = datetime.now().time() >= MARKET_CLOSE

    for _, trade in df.iterrows():

        if trade["status"] == "CLOSED":
            updated_trades.append(trade)
            continue

        stock = trade["stock_name"]
        symbol = f"NSE:{stock}-EQ"
        trade["remaining_qty"] = max(0, int(trade["remaining_qty"]))
        trade["sl_hit_today"] = _as_bool(trade.get("sl_hit_today"))
        trade["t1_hit"] = _as_bool(trade.get("t1_hit"))

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
        # SL trigger detection
        # ------------------------------
        if not trade["sl_hit_today"] and trade.get("current_sl") and ltp <= trade["current_sl"]:
            trade["sl_hit_today"] = True
            message = (
        f"🔴 <b>SL TRIGGERED</b>\n\n"
        f"<b>Stock:</b> {stock}\n"
        f"<b>LTP:</b> {ltp}\n"
        f"<b>SL:</b> {trade['current_sl']}\n"
        f"<b>Remaining Qty:</b> {trade['remaining_qty']}\n"
        f"Exit at day close"
    )

            mstock_send_telegram_message(message)
            logger.info("%s SL triggered today at LTP %.2f", stock, ltp)

        # ------------------------------
        # Day-SL exit (evening run, after close)
        # ------------------------------
        if trade["sl_hit_today"]:
            if not is_market_close:
                logger.info("%s SL triggered today, waiting for day end", stock)
                updated_trades.append(trade)
                continue

            result = _sell(stock, trade["remaining_qty"], "DAY_SL_EXIT")
            if result:
                _close(trade, "SL_DAY_EXIT", result, ltp)
                note = "AMO queued, fills at next open" if result["pending"] else f"Filled @ {trade['exit_price']}"
                mstock_send_telegram_message(
                    f"🔻 <b>SL DAY EXIT</b>\n\n"
                    f"<b>Stock:</b> {stock}\n"
                    f"<b>LTP:</b> {ltp}\n"
                    f"{note}"
                )
                logger.info("%s exited at day close due to SL.", stock)
            updated_trades.append(trade)
            continue

        # ------------------------------
        # T1 partial booking
        # ------------------------------
        if not trade["t1_hit"] and ltp >= trade["target1"]:
            partial_qty = trade["remaining_qty"] // 2
            booked = 0

            # Single share: nothing to split, keep it running to T2
            if partial_qty > 0:
                result = _sell(stock, partial_qty, "T1_PARTIAL")
                if not result:
                    updated_trades.append(trade)
                    continue
                booked = result["filled_qty"] or partial_qty
                trade["remaining_qty"] = max(0, trade["remaining_qty"] - booked)
                trade["t1_exit_price"] = result["avg_price"] or ltp

            trade["t1_hit"] = True
            trade["current_sl"] = trade["entry_price"]  # move SL to breakeven

            message = (
    f"🟢 <b>T1 HIT - PARTIAL BOOKED</b>\n\n"
    f"<b>Stock:</b> {stock}\n"
    f"<b>LTP:</b> {ltp}\n"
    f"<b>Booked Qty:</b> {booked}\n"
    f"<b>Remaining Qty:</b> {trade['remaining_qty']}\n"
    f"<b>SL moved to:</b> {trade['entry_price']}"
)

            mstock_send_telegram_message(message)

            logger.info("%s T1 hit at %.2f", stock, ltp)

        # ------------------------------
        # T2 full exit
        # ------------------------------
        if trade["remaining_qty"] > 0 and ltp >= trade["target2"]:

            result = _sell(stock, trade["remaining_qty"], "T2_EXIT")
            if result:
                message = (
    f"🎯 <b>T2 TARGET HIT</b>\n\n"
    f"<b>Stock:</b> {stock}\n"
    f"<b>LTP:</b> {ltp}\n"
    f"<b>Exit Qty:</b> {trade['remaining_qty']}\n"
    f"<b>Trade Closed</b>"
)

                mstock_send_telegram_message(message)

                logger.info("%s T2 hit. Trade closed.", stock)

                _close(trade, "T2", result, ltp)

        elif trade["remaining_qty"] == 0:
            trade["status"] = "CLOSED"
            trade["exit_reason"] = "T1"
            trade["closed_at"] = datetime.now()

        updated_trades.append(trade)

    save_trades(pd.DataFrame(updated_trades))
