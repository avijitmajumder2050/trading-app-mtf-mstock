import logging
from app.config.mstock_auth import get_mstock_client
from app.services.mstock_trade_store import append_trade_row, update_trade_row
from datetime import datetime

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ==========================================================
# Generic Order Executor (Logs Payload + Response)
# ==========================================================

def place_order_with_logging(payload: dict):

    mstock = get_mstock_client()

    logger.info("ORDER PAYLOAD -> %s", payload)

    try:
        response = mstock.place_order(**payload)
        data = response.json()

        logger.info("ORDER RESPONSE -> %s", data)

        # Handle list response (MStock sometimes returns list)
        if isinstance(data, list):
            if len(data) == 0:
                logger.error("Empty response list")
                return None
            data = data[0]

        if not isinstance(data, dict):
            logger.error("Unexpected response format: %s", data)
            return None

        if data.get("status") == "success":
            order_id = data.get("data", {}).get("order_id")
            logger.info("Order placed successfully. ID: %s", order_id)
            return order_id

        logger.error("Order failed -> %s", data)
        return None

    except Exception:
        logger.exception("Order execution failed")
        return None


# ==========================================================
# ENTRY (MTF - NO BROKER SL)
# ==========================================================

def execute_mtf_entry(trade: dict):

    entry_payload = {
        "_variety": "REGULAR",
        "_tradingsymbol": f"{trade['stock_name']}-EQ",
        "_exchange": "NSE",
        "_transaction_type": "BUY",
        "_order_type": "MARKET",
        "_quantity": trade["qty"],
        "_product": "MTF",
        "_validity": "DAY",
        "_price": 0,
        "_trigger_price": 0,
        "_disclosed_quantity": 0,
        "_tag": "MTF_ENTRY"
    }

    entry_order_id = place_order_with_logging(entry_payload)

    if not entry_order_id:
        logger.error("Entry failed")
        return None

    # Save new trade (ONLY place where append is used)
    trade_row = {
        "stock_name": trade["stock_name"],
        "security_id": trade["security_id"],
        "entry_price": trade["entry_price"],
        "initial_sl": trade["sl"],
        "current_sl": trade["sl"],
        "target1": trade["target1"],
        "target2": trade["target2"],
        "qty": trade["qty"],
        "remaining_qty": trade["qty"],
        "entry_order_id": entry_order_id,
        "sl_hit_today": False,
        "t1_hit": False,
        "status": "ACTIVE",
        "exit_reason": "",
        "entry_date": datetime.now().strftime("%Y-%m-%d"),
        "created_at": datetime.now()
    }

    append_trade_row(trade_row)

    logger.info("MTF trade saved for monitoring (Logical SL enabled).")

    return {
        "entry_order_id": entry_order_id
    }


# ==========================================================
# FULL EXIT
# ==========================================================

def exit_full_position(trade: dict, reason="MANUAL_EXIT"):

    if trade["remaining_qty"] <= 0:
        logger.error("No remaining quantity to exit")
        return None

    exit_payload = {
        "_variety": "REGULAR",
        "_tradingsymbol": f"{trade['stock_name']}-EQ",
        "_exchange": "NSE",
        "_transaction_type": "SELL",
        "_order_type": "MARKET",
        "_quantity": trade["remaining_qty"],
        "_product": "MTF",
        "_validity": "DAY",
        "_price": 0,
        "_trigger_price": 0,
        "_disclosed_quantity": 0,
        "_tag": "MTF_EXIT"
    }

    exit_order_id = place_order_with_logging(exit_payload)

    if not exit_order_id:
        logger.error("Exit failed")
        return None

    # Update existing trade row
    trade["status"] = "CLOSED"
    trade["exit_reason"] = reason
    trade["remaining_qty"] = 0
    trade["closed_at"] = datetime.now()

    update_trade_row(trade)

    logger.info(
        "Position closed for %s | Reason: %s",
        trade["stock_name"],
        reason
    )

    return exit_order_id


# ==========================================================
# PARTIAL EXIT
# ==========================================================

def exit_partial_position(trade: dict, qty_to_exit: int):

    if qty_to_exit <= 0:
        logger.error("Invalid partial quantity")
        return None

    if qty_to_exit >= trade["remaining_qty"]:
        logger.error("Partial qty >= remaining qty. Use full exit.")
        return None

    exit_payload = {
        "_variety": "REGULAR",
        "_tradingsymbol": f"{trade['stock_name']}-EQ",
        "_exchange": "NSE",
        "_transaction_type": "SELL",
        "_order_type": "MARKET",
        "_quantity": qty_to_exit,
        "_product": "MTF",
        "_validity": "DAY",
        "_price": 0,
        "_trigger_price": 0,
        "_disclosed_quantity": 0,
        "_tag": "MTF_PARTIAL_EXIT"
    }

    exit_order_id = place_order_with_logging(exit_payload)

    if not exit_order_id:
        logger.error("Partial exit failed")
        return None

    # Update existing trade row
    trade["remaining_qty"] -= qty_to_exit

    update_trade_row(trade)

    logger.info(
        "Partial exit for %s | Qty: %s | Remaining: %s",
        trade["stock_name"],
        qty_to_exit,
        trade["remaining_qty"]
    )

    return exit_order_id

def cancel_order(order_id: str):
    mstock = get_mstock_client()
    try:
        response = mstock.cancel_order(_variety="REGULAR", _order_id=order_id)
        logger.info("CANCEL RESPONSE -> %s", response.json())
        return True
    except Exception:
        logger.exception("Cancel failed")
        return False