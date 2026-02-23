# app/services/selection_engine.py

import logging
import pandas as pd
import io

from app.services.mstock_s3_reader import read_ema_momentum_from_s3
from app.services.mstock_live import get_mstock_ltp
from app.services.mstock_intraday_chart import get_intraday_chart_csv

logger = logging.getLogger(__name__)


def select_and_rank_stocks(interval="5minute"):

    df = read_ema_momentum_from_s3()

    if df.empty:
        logger.warning("EMA file empty")
        return []

    df.columns = df.columns.str.strip()

    # --------------------------------
    # 1️⃣ Build symbol list
    # --------------------------------
    symbols = [f"NSE:{name}" for name in df["Stock Name"].tolist()]

    logger.info("Fetching LTP for %d stocks", len(symbols))

    live_data = get_mstock_ltp(symbols)

    if not live_data:
        logger.warning("No LTP data received")
        return []

    selected = []

    # --------------------------------
    # 2️⃣ Loop stocks
    # --------------------------------
    for _, row in df.iterrows():

        stock_name = row["Stock Name"]
        sec_id = str(row["Security ID"])
        scan_high = float(row["High"])

        symbol_key = f"NSE:{stock_name}"
        ltp_data = live_data.get(symbol_key)

        if not ltp_data:
            logger.info("%s → No LTP data", stock_name)
            continue

        ltp = ltp_data.get("last_price")

        if not ltp:
            logger.info("%s → LTP missing", stock_name)
            continue

        ltp = float(ltp)

        logger.info(
            "%s | LTP: %.2f | ScanHigh: %.2f",
            stock_name, ltp, scan_high
        )

        # --------------------------------
        # 3️⃣ Breakout condition
        # --------------------------------
        if ltp <= scan_high:
            logger.info("%s → Rejected (No ScanHigh Break)", stock_name)
            continue

        # --------------------------------
        # 4️⃣ Get intraday first candle
        # --------------------------------
        csv_data = get_intraday_chart_csv(
            symboltoken=sec_id,
            interval=interval
        )

        if not csv_data:
            logger.info("%s → No intraday data", stock_name)
            continue
        

        intraday_df = pd.read_csv(io.StringIO(csv_data))

        if intraday_df.empty:
            logger.info("%s → Intraday empty", stock_name)
            continue
        if len(intraday_df) < 3:
            logger.info("%s → Not enough candles yet", stock_name)
            continue

        first_candle_low = float(intraday_df.iloc[0]["low"])
        first_candle_high = float(intraday_df.iloc[0]["high"])
        # Previous fully closed candle
        previous_candle_high = float(intraday_df.iloc[-2]["high"])

        logger.info(
            "%s | FirstHigh: %.2f | FirstLow: %.2f",
            stock_name, first_candle_high, first_candle_low
        )

        # Break first candle high
        if ltp <= first_candle_high:
            logger.info("%s → Rejected (No ORB Break)", stock_name)
            continue
        if previous_candle_high >= first_candle_high:
            logger.info("%s → Rejected (Breakout already happened earlier)", stock_name)
            continue
        

        # --------------------------------
        # 6️⃣ SL logic
        # --------------------------------
        sl_price = first_candle_low

        if sl_price >= ltp:
            logger.info("%s → Rejected (Invalid SL)", stock_name)
            continue

        sl_percent = (
            (first_candle_high - sl_price) / first_candle_high
        ) * 100

        # --------------------------------
        # 8️⃣ Extension filter (loosened)
        # --------------------------------
        extension_percent = (
            (ltp - first_candle_high) / first_candle_high
        ) * 100

        logger.info(
            "%s | Extension %%: %.2f",
            stock_name, extension_percent
        )

        if extension_percent > 2:   # 🔥 increased from 0.5 to 2%
            logger.info("%s → Rejected (Too Extended)", stock_name)
            continue

        score = sl_percent + extension_percent

        logger.info("%s → ✅ SELECTED", stock_name)

        selected.append({
            "stock_name": stock_name,
            "security_id": sec_id,
            "entry": ltp,  # FIXED (was first_candle_high)
            "sl": sl_price,
            "sl_percent": round(sl_percent, 2),
            "score": round(score, 2)
        })

    # --------------------------------
    # 5️⃣ Rank by lowest score
    # --------------------------------
    ranked = sorted(selected, key=lambda x: x["score"])

    logger.info("Total breakout candidates: %d", len(ranked))

    return ranked
