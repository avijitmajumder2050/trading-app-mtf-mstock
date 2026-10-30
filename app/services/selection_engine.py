# app/services/selection_engine.py

import logging
import pandas as pd
import io

from app.services.mstock_s3_reader import read_ema_momentum_from_s3
from app.services.mstock_live import get_mstock_ltp
from app.services.mstock_intraday_chart import get_intraday_chart_csv

logger = logging.getLogger(__name__)

# Best rule in mStock 5m backtest (Jan-Oct 2026): scan-high break, no
# gap-down, entry <= 0.5% above scan high, SL (first candle low) <= 1.5%
MAX_EXTENSION_PCT = 0.5
MAX_SL_PCT = 1.5


def select_and_rank_stocks(interval="5minute"):

    df = read_ema_momentum_from_s3()

    if df.empty:
        logger.warning("EMA file empty")
        return []

    df.columns = df.columns.str.strip()

    # --------------------------------
    # 1️⃣ Build symbol list
    # --------------------------------
    symbols = [f"NSE:{name}-EQ" for name in df["Stock Name"].tolist()]
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

        symbol_key = f"NSE:{stock_name}-EQ"
        eq_key = f"NSE:{stock_name}-EQ"
        be_key = f"NSE:{stock_name}-BE"
        ltp_data = live_data.get(eq_key) or live_data.get(be_key)

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
        day_open = float(intraday_df.iloc[0]["open"])
        prev_day_close = float(row["Price"])  # scan-day close

        logger.info(
            "%s | Open: %.2f | PrevDayClose: %.2f | FirstHigh: %.2f | ScanHigh: %.2f | PrevClose: %.2f",
            stock_name,
            day_open,
            prev_day_close,
            first_candle_high,
            scan_high,
            previous_candle_close
        )

        # --------------------------------
        # 4️⃣ Gap-down filter
        # --------------------------------
        if day_open < prev_day_close:
            logger.info("%s → Rejected (Gap-down open)", stock_name)
            continue

        # --------------------------------
        # 5️⃣ Scan-high breakout (first-candle high NOT required:
        #     waiting for it made entries late and lost money in backtest)
        # --------------------------------
        if ltp <= scan_high:
            logger.info("%s → Rejected (ScanHigh not broken)", stock_name)
            continue

        breakout_level = scan_high

        # Fresh breakout check
        if previous_candle_close >= breakout_level:
            logger.info("%s → Rejected (Breakout already happened earlier)", stock_name)
            continue

        logger.info("%s → Fresh ScanHigh Breakout Confirmed ✅", stock_name)

        # --------------------------------
        # 5️⃣ Stop Loss Logic
        # --------------------------------
        sl_price = first_candle_low

        if sl_price >= ltp:
            logger.info("%s → Rejected (Invalid SL)", stock_name)
            continue

        sl_percent = ((ltp - sl_price) / ltp) * 100

        if sl_percent > MAX_SL_PCT:
            logger.info("%s → Rejected (SL %.2f%% > %.2f%%)", stock_name, sl_percent, MAX_SL_PCT)
            continue

        # --------------------------------
        # 6️⃣ Extension Filter (from ScanHigh)
        # --------------------------------
        extension_percent = ((ltp - breakout_level) / breakout_level) * 100

        logger.info(
            "%s | Extension %%: %.2f",
            stock_name, extension_percent
        )

        if extension_percent > MAX_EXTENSION_PCT:
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


# ==========================================================
# WEEKLY MODE (Mon/Tue entries, hold to Friday)
# Best in 1m backtest Jan-Oct 2026: 3 consecutive 1m closes
# above scan high, entry <= 0.5% above it, SL = day low (0.5-2%)
# ==========================================================
WEEKLY_SUSTAIN_CANDLES = 3
WEEKLY_MAX_EXT_PCT = 0.5
WEEKLY_MIN_SL_PCT = 0.5
WEEKLY_MAX_SL_PCT = 2.0


def _sustained_above(closes, level, candles):
    """True if the last `candles` + 1 completed closes (cross + sustain) are all above level."""
    recent = closes[-(candles + 1):]
    return len(recent) == candles + 1 and all(close > level for close in recent)


def select_weekly_breakouts(exclude=()):

    df = read_ema_momentum_from_s3()

    if df.empty:
        logger.warning("EMA file empty")
        return []

    df.columns = df.columns.str.strip()
    df = df[~df["Stock Name"].isin(set(exclude))]

    if df.empty:
        return []

    symbols = [f"NSE:{name}-EQ" for name in df["Stock Name"].tolist()]
    live_data = get_mstock_ltp(symbols)

    if not live_data:
        logger.warning("No LTP data received")
        return []

    now_minute = pd.Timestamp.now().floor("min")
    selected = []

    for _, row in df.iterrows():

        stock_name = row["Stock Name"]
        sec_id = str(row["Security ID"])
        scan_high = float(row["High"])

        ltp_data = live_data.get(f"NSE:{stock_name}-EQ") or live_data.get(f"NSE:{stock_name}-BE")
        ltp = float((ltp_data or {}).get("last_price") or 0)

        if not ltp:
            logger.info("%s → No LTP data", stock_name)
            continue

        # Not above scan high, or already too far above it
        extension_percent = ((ltp - scan_high) / scan_high) * 100
        if extension_percent <= 0:
            continue
        if extension_percent > WEEKLY_MAX_EXT_PCT:
            logger.info("%s → Rejected (%.2f%% above ScanHigh)", stock_name, extension_percent)
            continue

        csv_data = get_intraday_chart_csv(symboltoken=sec_id, interval="minute")
        if not csv_data:
            logger.info("%s → No 1m data", stock_name)
            continue

        candles = pd.read_csv(io.StringIO(csv_data))
        candles["timestamp"] = pd.to_datetime(candles["timestamp"]).dt.tz_localize(None)

        # Only completed 1m candles count towards the sustain check
        completed = candles[candles["timestamp"] < now_minute]

        band = scan_high * (1 + WEEKLY_MAX_EXT_PCT / 100)
        if completed.empty or not scan_high < float(completed["close"].iloc[-1]) <= band:
            continue

        if not _sustained_above(completed["close"].tolist(), scan_high, WEEKLY_SUSTAIN_CANDLES):
            logger.info("%s → Waiting (not sustained %d min above ScanHigh)", stock_name, WEEKLY_SUSTAIN_CANDLES)
            continue

        sl_price = float(candles["low"].min())
        sl_percent = ((ltp - sl_price) / ltp) * 100

        if not WEEKLY_MIN_SL_PCT <= sl_percent <= WEEKLY_MAX_SL_PCT:
            logger.info("%s → Rejected (SL %.2f%% outside %.1f-%.1f%%)",
                        stock_name, sl_percent, WEEKLY_MIN_SL_PCT, WEEKLY_MAX_SL_PCT)
            continue

        logger.info(
            "%s → ✅ WEEKLY SELECTED | LTP %.2f | ScanHigh %.2f | Ext %.2f%% | SL %.2f (%.2f%%)",
            stock_name, ltp, scan_high, extension_percent, sl_price, sl_percent
        )

        selected.append({
            "stock_name": stock_name,
            "security_id": sec_id,
            "entry": ltp,
            "sl": sl_price,
            "sl_percent": round(sl_percent, 2),
            "score": round(extension_percent, 2)
        })

    # Closest to the scan high first
    return sorted(selected, key=lambda x: x["score"])
