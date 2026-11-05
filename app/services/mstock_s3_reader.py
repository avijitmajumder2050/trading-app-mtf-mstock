#app/services/mstock_s3_reader.py
import logging
import pandas as pd
import io
from datetime import datetime, timedelta
from app.config.settings import  EMA_MOMENTUM_FILE_KEY
from app.config.aws_s3 import s3 ,S3_BUCKET

logger = logging.getLogger(__name__)


def read_ema_momentum_from_s3(whole_week: bool = False) -> pd.DataFrame:
    """
    Reads ema_momentum_EOD.csv from S3 and returns DataFrame.

    Default: rows of the latest scan date only.
    whole_week=True: every row scanned this Mon-Sun week, plus the latest
    scan date (so Friday's signals are still live on Monday). Adds a
    "_scan_date" column so callers can skip signals already traded.
    """

    try:
        obj = s3.get_object(
            Bucket=S3_BUCKET,
            Key=EMA_MOMENTUM_FILE_KEY
        )

        df = pd.read_csv(io.BytesIO(obj["Body"].read()))
        df.columns = df.columns.str.strip()

        logger.info(
            f"Loaded EMA momentum file. Rows: {len(df)}"
        )

        # File accumulates several scan days; a setup is valid only for
        # the session after its scan, so keep the latest scan date only
        if "Scan Time" in df.columns:
            scan_date = pd.to_datetime(df["Scan Time"], errors="coerce").dt.date
            latest = scan_date.max()
            if pd.notna(latest) and whole_week:
                today = datetime.now().date()
                week_start = today - timedelta(days=today.weekday())
                keep = (scan_date >= week_start) | (scan_date == latest)
                df = df[keep].copy()
                df["_scan_date"] = scan_date[keep]
                df = df.reset_index(drop=True)
                logger.info(f"Using scans from {week_start} plus latest {latest}. Rows: {len(df)}")
            elif pd.notna(latest):
                df = df[scan_date == latest].reset_index(drop=True)
                logger.info(f"Using scan date {latest}. Rows: {len(df)}")

        return df

    except Exception:
        logger.exception("Failed to read EMA momentum file from S3")
        return pd.DataFrame()
