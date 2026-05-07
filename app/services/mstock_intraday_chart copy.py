import logging
import pandas as pd
from app.config.mstock_auth import get_mstock_client

logger = logging.getLogger(__name__)


def get_intraday_chart_csv(
    symboltoken: str,
    interval: str= "5minute",
    exchange: str = "1"  # Default NSE
) -> str:
    """
    Fetch intraday chart and return CSV string.

    exchange:
        1 - NSE (default)
        2 - NFO
        3 - CDS
        4 - BSE
        5 - BFO

    interval:
        minute, 3minute, 5minute, 10minute,
        15minute, 30minute, 60minute, day
    """

    try:
        mconnect = get_mstock_client()

        response = mconnect.get_intraday_chart(
            exchange,
            symboltoken,
            interval
        )

        if not response:
            logger.error("Intraday API returned None")
            return ""

        data = response.json()

        if data.get("status") != "success":
            logger.error(f"Intraday API failed: {data}")
            return ""

        candles = data.get("data", {}).get("candles", [])

        if not candles:
            logger.warning("No candle data found")
            return ""

        df = pd.DataFrame(
            candles,
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp")

        return df.to_csv(index=False)

    except Exception:
        logger.exception("Error fetching intraday CSV")
        return ""
