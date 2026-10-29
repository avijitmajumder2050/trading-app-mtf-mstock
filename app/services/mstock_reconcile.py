import logging
from collections import defaultdict
from app.config.mstock_auth import get_mstock_client
from app.services.mstock_trade_store import load_trades
from app.services.mstock_telegram_sender import mstock_send_telegram_message

logger = logging.getLogger(__name__)

MTF_PRODUCTS = {"F", "MTF"}
CNC_PRODUCTS = {"C", "CNC"}


def _base_symbol(symbol):
    # Broker reports both "GANDHAR" and "GANDHAR-EQ"
    symbol = str(symbol).upper()
    return symbol[:-3] if symbol.endswith("-EQ") else symbol


def _int(value):
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def get_broker_positions():
    """
    MTF: net positions (product F). CNC: shares already in holdings
    (incl. T1) plus today's CNC buys still in net positions.
    """
    client = get_mstock_client()
    data = client.get_net_position().json()
    if data.get("status") != "success":
        raise RuntimeError(f"Net position fetch failed: {data}")

    positions = defaultdict(int)
    for row in (data.get("data") or {}).get("net") or []:
        product = str(row.get("product", "")).upper()
        symbol = _base_symbol(row.get("tradingsymbol"))
        if product in MTF_PRODUCTS:
            positions[symbol] += _int(row.get("quantity"))
        elif product in CNC_PRODUCTS:
            # overnight part is already counted in holdings
            positions[symbol] += _int(row.get("quantity")) - _int(row.get("overnight_quantity"))

    holdings = client.get_holdings().json()
    if holdings.get("status") != "success":
        raise RuntimeError(f"Holdings fetch failed: {holdings}")
    for row in holdings.get("data") or []:
        positions[_base_symbol(row.get("tradingsymbol"))] += _int(row.get("quantity")) + _int(row.get("t1_quantity"))

    return {s: q for s, q in positions.items() if q}


def reconcile_positions():
    """
    Compare broker positions (MTF + CNC) with ACTIVE trades in active_trades.csv
    and alert on Telegram when they differ. Alert only — places no orders.
    Never raises: main.py must still reach EC2 termination.
    """
    try:
        _reconcile()
    except Exception:
        logger.exception("Reconciliation failed")
        mstock_send_telegram_message("⚠️ <b>RECONCILIATION FAILED</b>\n\nCheck broker positions manually.")


def _reconcile():
    broker = get_broker_positions()

    df = load_trades()
    tracked = defaultdict(int)
    bot_symbols = set()
    if not df.empty:
        bot_symbols = {_base_symbol(s) for s in df["stock_name"].dropna()}
        active = df[df["status"] != "CLOSED"]
        for _, trade in active.iterrows():
            tracked[_base_symbol(trade["stock_name"])] += max(0, int(trade["remaining_qty"]))

    # Only stocks the bot has traded: other delivery holdings are the user's own
    mismatches = [
        (symbol, broker.get(symbol, 0), tracked.get(symbol, 0))
        for symbol in sorted((set(broker) & bot_symbols) | set(tracked))
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
