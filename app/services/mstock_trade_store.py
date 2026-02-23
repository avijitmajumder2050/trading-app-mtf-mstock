import pandas as pd
import boto3
import logging
from io import StringIO
from datetime import datetime

# --------------------------------------------------
# Logging Setup
# --------------------------------------------------

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --------------------------------------------------
# S3 Config
# --------------------------------------------------

BUCKET = "dhan-trading-data"
KEY = "uploads/active_trades.csv"

s3 = boto3.client("s3")


# --------------------------------------------------
# Load Trades
# --------------------------------------------------

def load_trades():
    try:
        logger.info("Loading trades from S3 -> %s/%s", BUCKET, KEY)

        obj = s3.get_object(Bucket=BUCKET, Key=KEY)
        df = pd.read_csv(obj["Body"])

        logger.info("Loaded %s trades", len(df))
        return df

    except s3.exceptions.NoSuchKey:
        logger.warning("No active_trades.csv found in S3. Creating new DataFrame.")
        return pd.DataFrame()

    except Exception:
        logger.exception("Failed to load trades from S3")
        return pd.DataFrame()


# --------------------------------------------------
# Save Trades
# --------------------------------------------------

def save_trades(df):
    try:
        df["last_update"] = datetime.now()

        logger.info("Saving %s trades to S3", len(df))

        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)

        s3.put_object(
            Bucket=BUCKET,
            Key=KEY,
            Body=csv_buffer.getvalue()
        )

        logger.info("Trades successfully saved to S3")

    except Exception:
        logger.exception("Failed to save trades to S3")


# --------------------------------------------------
# Append Trade Row (ONLY FOR NEW ENTRY)
# --------------------------------------------------

def append_trade_row(row_dict):
    try:
        logger.info("Appending NEW trade -> %s", row_dict.get("stock_name"))

        df = load_trades()

        # Prevent duplicate entry_order_id
        if not df.empty and "entry_order_id" in df.columns:
            if row_dict.get("entry_order_id") in df["entry_order_id"].values:
                logger.warning("Trade already exists. Skipping append.")
                return

        df = pd.concat([df, pd.DataFrame([row_dict])], ignore_index=True)

        save_trades(df)
        logger.info("New trade appended successfully")

    except Exception:
        logger.exception("Failed to append trade row")


# --------------------------------------------------
# Update Trade Row (FOR PARTIAL EXIT / SL / CLOSE)
# --------------------------------------------------

def update_trade_row(updated_trade):
    try:
        logger.info("Updating trade -> %s", updated_trade.get("stock_name"))

        df = load_trades()

        if df.empty:
            logger.error("No trades available to update")
            return

        if "entry_order_id" not in df.columns:
            logger.error("entry_order_id column missing")
            return

        mask = df["entry_order_id"] == updated_trade["entry_order_id"]

        if not mask.any():
            logger.error("Trade not found for update")
            return

        for key, value in updated_trade.items():
            df.loc[mask, key] = value

        save_trades(df)
        logger.info("Trade updated successfully")

    except Exception:
        logger.exception("Failed to update trade row")
