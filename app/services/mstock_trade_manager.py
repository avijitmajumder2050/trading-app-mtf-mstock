import logging
from datetime import datetime
from app.config.mstock_auth import get_mstock_client
from app.services.mstock_order_executor import place_order_with_logging, cancel_order
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ==========================================================
# MAIN TRADE MANAGEMENT ENGINE
# ==========================================================

def manage_active_trades(active_trades_df):

    mstock = get_mstock_client()

    symbols = [f"NSE:{row['stock_name']}-EQ" for _, row in active_trades_df.iterrows()]
    ltp_response = mstock.get_ltp(symbols)
    ltp_data = ltp_response.json()["data"]

    updated_trades = []

    for _, trade in active_trades_df.iterrows():

        stock = trade["stock_name"]
        
        ltp = float(ltp_data.get(f"NSE:{stock}-EQ", {}).get("last_price", 0))

        entry = float(trade["entry_price"])
        current_sl = float(trade["current_sl"])
        target1 = float(trade["target1"])
        target2 = float(trade["target2"])
        remaining_qty = int(trade["remaining_qty"])
        sl_order_id = trade["sl_order_id"]

        risk = entry - trade["initial_sl"]

        # ==================================================
        # 1️⃣ FINAL TARGET HIT
        # ==================================================
        if ltp >= target2:

            cancel_order(sl_order_id)

            exit_payload = {
                "_variety": "REGULAR",
                "_tradingsymbol": f"{stock}-EQ",
                "_exchange": "NSE",
                "_transaction_type": "SELL",
                "_order_type": "MARKET",
                "_quantity": remaining_qty,
                "_product": "MTF",
                "_validity": "DAY",
                "_price": 0,
                "_trigger_price": 0,
                "_disclosed_quantity": 0,
                "_tag": "ORB_T2_EXIT"
            }

            place_order_with_logging(exit_payload)

            trade["status"] = "CLOSED"
            trade["exit_reason"] = "T2"
            updated_trades.append(trade)
            continue


        # ==================================================
        # 2️⃣ TARGET 1 PARTIAL BOOKING
        # ==================================================
        if not trade["t1_hit"] and ltp >= target1:

            cancel_order(sl_order_id)

            partial_qty = remaining_qty // 2

            # Partial Sell
            partial_payload = {
                "_variety": "REGULAR",
                "_tradingsymbol": f"{stock}-EQ",
                "_exchange": "NSE",
                "_transaction_type": "SELL",
                "_order_type": "MARKET",
                "_quantity": partial_qty,
                "_product": "MTF",
                "_validity": "DAY",
                "_price": 0,
                "_trigger_price": 0,
                "_disclosed_quantity": 0,
                "_tag": "ORB_T1_BOOK"
            }

            place_order_with_logging(partial_payload)

            remaining_qty = remaining_qty - partial_qty

            # Move SL to Breakeven
            new_sl = entry

            new_sl_payload = {
                "_variety": "REGULAR",
                "_tradingsymbol": f"{stock}-EQ",
                "_exchange": "NSE",
                "_transaction_type": "SELL",
                "_order_type": "SL-M",
                "_quantity": remaining_qty,
                "_product": "MTF",
                "_validity": "DAY",
                "_price": 0,
                "_trigger_price": new_sl,
                "_disclosed_quantity": 0,
                "_tag": "ORB_TRAIL_SL"
            }

            new_sl_id = place_order_with_logging(new_sl_payload)

            trade["remaining_qty"] = remaining_qty
            trade["sl_order_id"] = new_sl_id
            trade["current_sl"] = new_sl
            trade["t1_hit"] = True


        # ==================================================
        # 3️⃣ ADVANCED TRAILING (1R Based)
        # ==================================================

        one_r = risk
        two_r = entry + (2 * one_r)
        three_r = entry + (3 * one_r)

        new_sl = current_sl

        if ltp >= two_r:
            new_sl = entry + one_r

        if ltp >= three_r:
            new_sl = entry + (2 * one_r)

        # Update SL only if improved
        if new_sl > current_sl:

            cancel_order(sl_order_id)

            trail_payload = {
                "_variety": "REGULAR",
                "_tradingsymbol": f"{stock}-EQ",
                "_exchange": "NSE",
                "_transaction_type": "SELL",
                "_order_type": "SL-M",
                "_quantity": remaining_qty,
                "_product": "MTF",
                "_validity": "DAY",
                "_price": 0,
                "_trigger_price": new_sl,
                "_disclosed_quantity": 0,
                "_tag": "ORB_TRAIL_UPDATE"
            }

            new_sl_id = place_order_with_logging(trail_payload)

            trade["current_sl"] = new_sl
            trade["sl_order_id"] = new_sl_id


        # ==================================================
        # 4️⃣ TIME EXIT (5 Days)
        # ==================================================

        entry_date = datetime.strptime(trade["entry_date"], "%Y-%m-%d")
        days_in_trade = (datetime.now() - entry_date).days

        if days_in_trade >= 5:

            cancel_order(trade["sl_order_id"])

            exit_payload = {
                "_variety": "REGULAR",
                "_tradingsymbol": f"{stock}-EQ",
                "_exchange": "NSE",
                "_transaction_type": "SELL",
                "_order_type": "MARKET",
                "_quantity": remaining_qty,
                "_product": "MTF",
                "_validity": "DAY",
                "_price": 0,
                "_trigger_price": 0,
                "_disclosed_quantity": 0,
                "_tag": "ORB_TIME_EXIT"
            }

            place_order_with_logging(exit_payload)

            trade["status"] = "CLOSED"
            trade["exit_reason"] = "TIME_EXIT"

        updated_trades.append(trade)

    return updated_trades
