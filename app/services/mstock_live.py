# app/services/mstock_intraday_chart.py
import logging
from app.config.mstock_auth import get_mstock_client

logger = logging.getLogger(__name__)

def get_mstock_ltp(symbols):
    """
    symbols format:
    [
        "NSE:ACC-EQ",
        "NSE:TCS-EQ"
    ]

    Auto fallback:
    EQ -> BE
    """

    try:

        mconnect = get_mstock_client()

        final_data = {}

        for symbol in symbols:

            try:

                # -------------------------
                # Try EQ first
                # -------------------------
                response = mconnect.get_ltp([symbol])

                data = response.json()

                if data.get("status") == "success" and data.get("data"):

                    final_data.update(data.get("data", {}))

                    logger.info(f"LTP success: {symbol}")

                    continue

                # -------------------------
                # Try BE fallback
                # -------------------------
                if symbol.endswith("-EQ"):

                    be_symbol = symbol.replace("-EQ", "-BE")

                    logger.warning(
                        f"{symbol} failed. Trying {be_symbol}"
                    )

                    response = mconnect.get_ltp([be_symbol])

                    data = response.json()

                    if data.get("status") == "success" and data.get("data"):

                        final_data.update(data.get("data", {}))

                        logger.info(
                            f"LTP success with BE: {be_symbol}"
                        )

                        continue

                logger.error(f"LTP failed: {symbol}")

            except Exception as inner_e:

                # fallback to BE on invalid symbol
                if symbol.endswith("-EQ"):

                    try:

                        be_symbol = symbol.replace("-EQ", "-BE")

                        

                        response = mconnect.get_ltp([be_symbol])

                        data = response.json()

                        if data.get("status") == "success" and data.get("data"):

                            final_data.update(data.get("data", {}))

                            logger.info(
                                f"LTP success with BE: {be_symbol}"
                            )

                            continue

                    except Exception as be_error:

                        logger.error(
                            f"BE fallback failed for {symbol}: {be_error}"
                        )

                logger.error(
                    f"Error fetching LTP for {symbol}: {inner_e}"
                )

        return final_data

    except Exception as e:

        logger.error(f"Error fetching LTP: {e}")

        return {}