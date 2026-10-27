import logging
from collections import defaultdict
from app.config.mstock_auth import get_mstock_client
from app.services.mstock_trade_store import load_trades
from app.services.mstock_telegram_sender import mstock_send_telegram_message

logger = logging.getLogger(__name__)

MTF_PRODUCTS = {"F", "MTF"}


def _base_symbol(symbol):
    # Broker reports both "GANDHAR" and "GANDHAR-EQ"
    symbol = str(symbol).upper()
    return symbol[:-3] if symbol.endswith("-EQ") else symbol


def get_broker_mtf_positions():
    data = get_mstock_client().get_net_position().json()
    if data.get("status") != "success":
        raise RuntimeError(f"Net position fetch failed: {data}")

    positions = defaultdict(int)
    for row in (data.get("data") or {}).get("net") or []:
        if str(row.get("product", "")).upper() not in MTF_PRODUCTS:
            continue
        qty = int(row.get("quantity") or 0)
        if qty:
            positions[_base_symbol(row.get("tradingsymbol"))] += qty
    return dict(positions)


def reconcile_positions():
    """
    Compare broker MTF positions with ACTIVE trades in active_trades.csv
    and alert on Telegram when they differ. Alert only — places no orders.
    Never raises: main.py must still reach EC2 termination.
    """
    try:
        _reconcile()
    except Exception:
        logger.exception("Reconciliation failed")
        mstock_send_telegram_message("⚠️ <b>RECONCILIATION FAILED</b>\n\nCheck broker positions manually.")


def _reconcile():
    broker = get_broker_mtf_positions()

    df = load_trades()
    tracked = defaultdict(int)
    if not df.empty:
        active = df[df["status"] != "CLOSED"]
        for _, trade in active.iterrows():
            tracked[_base_symbol(trade["stock_name"])] += max(0, int(trade["remaining_qty"]))

    mismatches = [
        (symbol, broker.get(symbol, 0), tracked.get(symbol, 0))
        for symbol in sorted(set(broker) | set(tracked))
        if broker.get(symbol, 0) != tracked.get(symbol, 0)
    ]

    if not mismatches:
        logger.info("Reconciliation OK: broker positions match active trades")
        return

    lines = "\n".join(f"<b>{s}</b>: broker {b} | bot {t}" for s, b, t in mismatches)
    mstock_send_telegram_message(
        f"⚠️ <b>POSITION MISMATCH</b>\n\n"
        f"{lines}\n\n"
        f"Untracked broker qty has no SL/target management."
    )
    logger.warning("Reconciliation mismatches: %s", mismatches)
