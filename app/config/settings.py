# app/config/settings.py

import os
from pytz import timezone
from datetime import time

from app.config.aws_ssm import get_param
from app.config.aws_s3 import S3_BUCKET   # Import detected bucket

# --- Timezone ---
IST = timezone("Asia/Kolkata")

# --- Scan Times ---
INSIDEBAR_SCAN_TIME = time(9, 31)

# --- Trading Window (FROM SSM, no redeploy needed to change) ---
def _parse_time(value: str, fallback: time) -> time:
    try:
        h, m = value.strip().split(":")
        return time(int(h), int(m))
    except Exception:
        return fallback

ENTRY_START = _parse_time(
    get_param("/trading-app-mtf/schedule/entry_start", decrypt=False, default="09:31"),
    time(9, 31),
)
ENTRY_END = _parse_time(
    get_param("/trading-app-mtf/schedule/entry_end", decrypt=False, default="11:25"),
    time(11, 25),
)
EVENING_TIME = _parse_time(
    get_param("/trading-app-mtf/schedule/evening_time", decrypt=False, default="16:30"),
    time(16, 30),
)

# --- AWS Config ---
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")

# Bucket comes from aws_s3.py
# S3_BUCKET = auto detected

# S3 object keys
MAP_FILE_KEY = "uploads/mapping.csv"
NIFTYMAP_FILE_KEY = "uploads/nifty_mapping.csv"

CANDLE_FILE_KEY = "uploads/inside_bar_15min_data_RS80.csv"
FILTERED_FILE_KEY = "uploads/inside_bar_15min_RS80.csv"

EOD_DATA_PREFIX = "eod_data"

# Uploads folder
S3_UPLOADS_PREFIX = "uploads"

# Files
EMA_MOMENTUM_FILE_KEY = f"{S3_UPLOADS_PREFIX}/ema_momentum_EOD.csv"
NIFTY_BREAKOUT_FILE_KEY = f"{S3_UPLOADS_PREFIX}/nifty_15m_breakout_signals.csv"
FYERS_BREAKOUT_FILE_KEY = f"{S3_UPLOADS_PREFIX}/fyer_insiderbar_brekout.csv"
TRADE_JOURNAL_FILE_KEY = f"{S3_UPLOADS_PREFIX}/fyers_trade_journal.csv"

# --- Logs ---
LOG_DIR = "logs"

# =========================
# TELEGRAM (FROM SSM)
# =========================
BOT_TOKEN = get_param("/trading-bot/telegram/BOT_TOKEN", decrypt=True)
CHAT_ID = get_param("/trading-bot/telegram/CHAT_ID")

# --- Telegram Keywords ---
TRIGGER_KEYWORDS = ["scanner", "scan", "momentum", "interday", "intraday"]
SWING_KEYWORDS = ["swing", "position"]
CROSS_KEYWORDS = ["ema cross", "cross ema", "ema crossover", "crossover"]