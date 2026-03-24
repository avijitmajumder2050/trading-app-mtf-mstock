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
        # 3️⃣ Get intraday data
        # --------------------------------
        csv_data = get_intraday_chart_csv(
            symboltoken=sec_id,
            interval=interval
        )

        if not csv_data:
            logger.info("%s → No intraday data", stock_name)
            continue

        intraday_df = pd.read_csv(io.StringIO(csv_data))

        if intraday_df.empty or len(intraday_df) < 3:
            logger.info("%s → Not enough candles yet", stock_name)
            continue

        first_candle_low = float(intraday_df.iloc[0]["low"])
        first_candle_high = float(intraday_df.iloc[0]["high"])
        previous_candle_close = float(intraday_df.iloc[-2]["close"])

        logger.info(
            "%s | FirstHigh: %.2f | ScanHigh: %.2f | PrevClose: %.2f",
            stock_name,
            first_candle_high,
            scan_high,
            previous_candle_close
        )

        # --------------------------------
        # 4️⃣ Dual Breakout Logic (Order Independent)
        # --------------------------------
        orb_break = ltp > first_candle_high
        scan_break = ltp > scan_high

        if not (orb_break and scan_break):
            logger.info("%s → Rejected (Both ORB and ScanHigh not broken)", stock_name)
            continue


        orb_high = first_candle_high
        scan_high_level = scan_high
        
        breakout_level = max(first_candle_high, scan_high)
        logger.info(
    "%s | ORB: %.2f | ScanHigh: %.2f | BreakoutLevel: %.2f | PrevClose: %.2f | LTP: %.2f",
    stock_name,
    orb_high,
    scan_high_level,
    breakout_level,
    previous_candle_close,
    ltp
)
        

        # Fresh breakout check
        if previous_candle_close >= breakout_level:
            logger.info("%s → Rejected (Breakout already happened earlier)", stock_name)
            continue

        logger.info("%s → Fresh Dual Breakout Confirmed ✅", stock_name)

        # --------------------------------
        # 5️⃣ Stop Loss Logic
        # --------------------------------
        sl_price = first_candle_low

        if sl_price >= ltp:
            logger.info("%s → Rejected (Invalid SL)", stock_name)
            continue

        sl_percent = ((ltp - sl_price) / ltp) * 100

        # --------------------------------
        # 6️⃣ Extension Filter
        # --------------------------------
        extension_percent = ((ltp - breakout_level) / breakout_level) * 100

        logger.info(
            "%s | Extension %%: %.2f",
            stock_name, extension_percent
        )

        if extension_percent > 2:
            logger.info("%s → Rejected (Too Extended)", stock_name)
            continue

        score = sl_percent + extension_percent

        logger.info("%s → ✅ SELECTED", stock_name)

        selected.append({
            "stock_name": stock_name,
            "security_id": sec_id,
            "entry": ltp,
            "sl": sl_price,
            "sl_percent": round(sl_percent, 2),
            "score": round(score, 2)
        })

    # --------------------------------
    # 7️⃣ Rank by lowest score
    # --------------------------------
    ranked = sorted(selected, key=lambda x: x["score"])

    logger.info("Total breakout candidates: %d", len(ranked))

    return ranked
