# app/services/rule_engine.py

import logging
from app.broker.position_sizing import calculate_mstock_position_size

logger = logging.getLogger(__name__)


def enrich_with_trade_rules(ranked_stocks, max_loss_per_trade=1000):

    trade_setups = []
    logger.info("Starting position sizing for %d stocks", len(ranked_stocks))
    logger.info("Max loss per trade: ₹%s", max_loss_per_trade)

    for stock in ranked_stocks:

        entry = float(stock["entry"])
        sl = float(stock["sl"])
        sec_id = stock["security_id"]
        stock_name = stock["stock_name"]
        logger.info("Processing stock: %s", stock_name)
        logger.info("Entry: %.2f | SL: %.2f", entry, sl)

        if sl >= entry:
            logger.warning(f"{stock_name} skipped (invalid SL)")
            continue

        # Risk per share
        risk_per_share = entry - sl

        # Targets
        target1 = entry + risk_per_share
        target2 = entry + (risk_per_share * 2)
        logger.info(
            "%s | Target1: %.2f | Target2: %.2f",
            stock_name, target1, target2
        )

        # Position sizing
        qty, risk_amt, value = calculate_mstock_position_size(
            price=entry,
            entry=entry,
            sl=sl,
            sec_id=sec_id,
            max_loss=max_loss_per_trade
        )
        
        logger.info(
            "%s | Qty: %s | Position Value: ₹%.2f | Risk Amt: ₹%.2f",
            stock_name, qty, value, risk_amt
        )

        if qty <= 0:
            logger.warning(f"{stock_name} skipped (qty=0)")
            continue

        trade_setups.append({
            "stock_name": stock_name,
            "security_id": sec_id,
            "entry_price": round(entry, 2),
            "sl": round(sl, 2),
            "target1": round(target1, 2),
            "target2": round(target2, 2),
            "risk_per_share": round(risk_per_share, 2),
            "sl_percent": stock["sl_percent"],
            "qty": qty,
            "max_loss": round(risk_amt, 2),
            "position_value": round(value, 2)
        })

    return trade_setups
