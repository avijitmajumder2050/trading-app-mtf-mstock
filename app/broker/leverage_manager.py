import logging
import pandas as pd
import io
import boto3

from app.config.settings import S3_BUCKET, NIFTYMAP_FILE_KEY,AWS_REGION,MAP_FILE_KEY
from app.config.aws_s3 import s3

logger = logging.getLogger(__name__)

_LEVERAGE_MAP = {}



def _load_leverage_from_s3():
    global _LEVERAGE_MAP

    obj = s3.get_object(Bucket=S3_BUCKET, Key=NIFTYMAP_FILE_KEY)
    df = pd.read_csv(io.BytesIO(obj["Body"].read()))

    if "Instrument ID" not in df.columns:
        raise ValueError("Instrument ID missing in leverage CSV")

    if "MIS_LEVERAGE" not in df.columns:
        logger.warning(" MIS_LEVERAGE missing, defaulting to 1")

    _LEVERAGE_MAP = dict(
        zip(
            df["Instrument ID"].astype(str),
            df.get("MIS_LEVERAGE", 1)
        )
    )

    logger.info(f" Loaded leverage for {len(_LEVERAGE_MAP)} instruments")


def init_leverage_cache(force=False):
    if force or not _LEVERAGE_MAP:
        _load_leverage_from_s3()
    return _LEVERAGE_MAP


def get_leverage(sec_id: str) -> float:
    if not _LEVERAGE_MAP:
        init_leverage_cache()

    lev = _LEVERAGE_MAP.get(str(sec_id), 1)

    if str(sec_id) not in _LEVERAGE_MAP:
        logger.warning(f" Missing leverage for {sec_id}, default=1")

    return float(lev)


# -----------------------------
# ✅ MStock MTF Leverage Support
# -----------------------------

_MSTOCK_LEVERAGE_MAP = {}


def _load_mstock_leverage_from_s3():
    global _MSTOCK_LEVERAGE_MAP

    obj = s3.get_object(Bucket=S3_BUCKET, Key=MAP_FILE_KEY)
    df = pd.read_csv(io.BytesIO(obj["Body"].read()))

    if "Instrument ID" not in df.columns:
        raise ValueError("Instrument ID missing in leverage CSV")

    if "mstock_MTF_Leverage" not in df.columns:
        logger.warning(" mstock_MTF_Leverage missing, defaulting to 1")

    _MSTOCK_LEVERAGE_MAP = dict(
        zip(
            df["Instrument ID"].astype(str),
            df.get("mstock_MTF_Leverage", 1)
        )
    )

    logger.info(f" Loaded mstock leverage for {len(_MSTOCK_LEVERAGE_MAP)} instruments")


def init_mstock_leverage_cache(force=False):
    if force or not _MSTOCK_LEVERAGE_MAP:
        _load_mstock_leverage_from_s3()
    return _MSTOCK_LEVERAGE_MAP


def get_mstock_leverage(sec_id: str) -> float:
    if not _MSTOCK_LEVERAGE_MAP:
        init_mstock_leverage_cache()

    lev = _MSTOCK_LEVERAGE_MAP.get(str(sec_id), 1)

    if str(sec_id) not in _MSTOCK_LEVERAGE_MAP:
        logger.warning(f" Missing mstock leverage for {sec_id}, default=1")
    
    # If leverage is 0 or invalid
    try:
        lev = float(lev)
        if lev <= 0:
            #logger.warning(f" Invalid mstock leverage ({lev}) for {sec_id}, default=1")
            return 1.0
        return lev
    except Exception:
        logger.warning(f" Error parsing leverage for {sec_id}, default=1")
        return 1.0

