# app/services/mstock_telegram_sender.py

import logging
import requests
from app.config.settings import BOT_TOKEN, CHAT_ID

TELEGRAM_FOOTER = (
    "\n\n⚠️ This is for educational purposes only. "
    "Not a buy/sell recommendation. Trade at your own risk."
)

def mstock_send_telegram_message(message: str):

    full_message = f"{message}{TELEGRAM_FOOTER}"

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": full_message,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(url, data=payload, timeout=5)

        if response.status_code != 200:
            logging.error("❌ Telegram error: %s", response.text)
        else:
            logging.info("📩 Sent alert successfully")

    except Exception as e:
        logging.error("❌ Telegram send error: %s", e)
