#app/config/mstock_auth.py
import logging
from tradingapi_a.mconnect import MConnect
from app.config.aws_ssm import get_param

logger = logging.getLogger(__name__)

_api_key = None
_access_token = None
_mstock_client = None


def get_mstock_client():
    global _api_key, _access_token, _mstock_client

    if _mstock_client:
        return _mstock_client

    # Load from SSM only once
    if not _api_key or not _access_token:
        _api_key = get_param("/mstock/api_key", decrypt=True)
        _access_token = get_param("/mstock/access_token", decrypt=True)

    # Create client
    mconnect = MConnect(debug=False)
    mconnect.set_api_key(_api_key)
    mconnect.set_access_token(_access_token)

    logger.info("Authenticated mStock client created")

    _mstock_client = mconnect
    return _mstock_client


# 🔥 Global instance (same style as dhan)
mstock = get_mstock_client()
