#app/services/mstock_s3_reader.py
import logging
import pandas as pd
import io
from app.config.settings import S3_BUCKET, EMA_MOMENTUM_FILE_KEY
from app.config.aws_s3 import s3

logger = logging.getLogger(__name__)


def read_ema_momentum_from_s3() -> pd.DataFrame:
    """
    Reads ema_momentum_EOD.csv from S3 and returns DataFrame
    """

    try:
        obj = s3.get_object(
            Bucket=S3_BUCKET,
            Key=EMA_MOMENTUM_FILE_KEY
        )

        df = pd.read_csv(io.BytesIO(obj["Body"].read()))

        logger.info(
            f"Loaded EMA momentum file. Rows: {len(df)}"
        )

        return df

    except Exception:
        logger.exception("Failed to read EMA momentum file from S3")
        return pd.DataFrame()
