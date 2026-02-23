import logging
import pandas as pd
import io
from datetime import datetime

from app.services.mstock_s3_reader import read_ema_momentum_from_s3
from app.services.mstock_intraday_chart import get_intraday_chart_csv
from app.config.settings import S3_BUCKET
from app.config.aws_s3 import s3

logger = logging.getLogger(__name__)


def generate_intraday_combined_file(
    interval: str = "5minute",
    exchange: str = "1"
):
    """
    Reads EMA file from S3:
    Stock Name | Security ID | Market Cap | ...

    Fetch intraday per Security ID
    Combine into single CSV
    Upload to S3 → uploads/
    """

    try:
        ema_df = read_ema_momentum_from_s3()

        if ema_df.empty:
            logger.warning("EMA momentum file empty")
            return

        # Normalize column names (safe handling)
        ema_df.columns = ema_df.columns.str.strip()

        required_cols = ["Security ID", "Stock Name"]

        for col in required_cols:
            if col not in ema_df.columns:
                logger.error(f"Missing required column: {col}")
                return

        combined_frames = []

        unique_rows = ema_df[["Security ID", "Stock Name"]].drop_duplicates()

        for _, row in unique_rows.iterrows():

            sec_id = str(row["Security ID"])
            stock_name = row["Stock Name"]

            logger.info(f"Fetching intraday for {stock_name} ({sec_id})")

            csv_data = get_intraday_chart_csv(
                symboltoken=sec_id,
                interval=interval,
                exchange=exchange
            )

            if not csv_data:
                logger.warning(f"No intraday data for {sec_id}")
                continue

            intraday_df = pd.read_csv(io.StringIO(csv_data))

            # Rename timestamp → datetime
            intraday_df.rename(columns={"timestamp": "datetime"}, inplace=True)

            # Add stock name & security id
            intraday_df["stock name"] = stock_name
            intraday_df["security id"] = sec_id

            combined_frames.append(intraday_df)

        if not combined_frames:
            logger.warning("No intraday data fetched")
            return

        final_df = pd.concat(combined_frames, ignore_index=True)

        # Ensure final column order
        final_df = final_df[
            ["datetime", "open", "high", "low", "close", "volume",
             "stock name", "security id"]
        ]

        today = datetime.now().strftime("%Y-%m-%d")
        file_key = f"uploads/intraday_combined.csv"

        csv_buffer = io.StringIO()
        final_df.to_csv(csv_buffer, index=False)

        s3.put_object(
            Bucket=S3_BUCKET,
            Key=file_key,
            Body=csv_buffer.getvalue()
        )

        logger.info(f"Uploaded combined intraday file : {file_key}")

    except Exception:
        logger.exception("Intraday combined file generation failed")
