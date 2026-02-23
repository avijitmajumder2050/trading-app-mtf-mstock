import logging
from app.config.mstock_auth import get_mstock_client

logger = logging.getLogger(__name__)

def get_mstock_ohlc(symbols):
    """
    symbols format:
    ["NSE:ACC", "BSE:ACC"]
    """

    try:
        mconnect = get_mstock_client()

        response = mconnect.get_ohlc(symbols)
        data = response.json()

        #logger.info(f"OHLC Raw Response: {data}")

        if data.get("status") == "success":
            return data.get("data", {})
        else:
            logger.error("mStock OHLC API failed")
            return {}

    except Exception as e:
        logger.error(f"Error fetching OHLC: {e}")
        return {}
