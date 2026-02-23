# app/services/mstock_intraday_chart.py
import logging
from app.config.mstock_auth import get_mstock_client

logger = logging.getLogger(__name__)

def get_mstock_ltp(symbols):
    """
    symbols format:
    ["NSE:ACC", "BSE:ACC"]
    """

    try:
        mconnect = get_mstock_client()

        response = mconnect.get_ltp(symbols)
        data = response.json()

        #logger.info(f"LTP Response: {data}")

        if data.get("status") == "success":
            return data.get("data", {})
        else:
            logger.error("mStock LTP API failed")
            return {}

    except Exception as e:
        logger.error(f"Error fetching LTP: {e}")
        return {}
