import logging
import pandas as pd
from app.config.mstock_auth import get_mstock_client

logger = logging.getLogger(__name__)


def get_intraday_chart_csv(
    symboltoken: str,
    interval: str = "5minute",
    exchange: str = "1"  # Default NSE EQ
) -> str:
    """
    Fetch intraday chart and return CSV string.

    exchange:
        1 - NSE EQ
        4 - NSE BE / BSE
        2 - NFO
        3 - CDS
        5 - BFO

    interval:
        minute, 3minute, 5minute, 10minute,
        15minute, 30minute, 60minute, day
    """

    try:

        mconnect = get_mstock_client()

        # --------------------------------
        # Try original exchange
        # --------------------------------
        response = mconnect.get_intraday_chart(
            exchange,
            symboltoken,
            interval
        )

        if not response:
            logger.warning(
                f"Intraday returned None for exchange={exchange}, token={symboltoken}"
            )

        else:

            data = response.json()

            if data.get("status") == "success":

                candles = data.get("data", {}).get("candles", [])

                if candles:

                    df = pd.DataFrame(
                        candles,
                        columns=[
                            "timestamp",
                            "open",
                            "high",
                            "low",
                            "close",
                            "volume"
                        ]
                    )

                    df["timestamp"] = pd.to_datetime(df["timestamp"])

                    df = df.sort_values("timestamp")

                    logger.info(
                        f"Intraday success: exchange={exchange}, token={symboltoken}"
                    )

                    return df.to_csv(index=False)

        # --------------------------------
        # Fallback NSE EQ -> BE/BSE
        # --------------------------------
        if exchange == "1":

            fallback_exchange = "4"

            logger.warning(
                f"NSE EQ failed for token={symboltoken}. Trying exchange=4"
            )

            response = mconnect.get_intraday_chart(
                fallback_exchange,
                symboltoken,
                interval
            )

            if response:

                data = response.json()

                if data.get("status") == "success":

                    candles = data.get("data", {}).get("candles", [])

                    if candles:

                        df = pd.DataFrame(
                            candles,
                            columns=[
                                "timestamp",
                                "open",
                                "high",
                                "low",
                                "close",
                                "volume"
                            ]
                        )

                        df["timestamp"] = pd.to_datetime(df["timestamp"])

                        df = df.sort_values("timestamp")

                        logger.info(
                            f"Intraday success with exchange=4, token={symboltoken}"
                        )

                        return df.to_csv(index=False)

        logger.error(
            f"Intraday failed for token={symboltoken}"
        )

        return ""

    except Exception as e:

        logger.exception(
            f"Error fetching intraday CSV for token={symboltoken}: {e}"
        )

        return ""