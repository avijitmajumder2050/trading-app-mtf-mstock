import logging
from app.config.dhan_auth import dhan
from app.config.mstock_auth import mstock  # ✅ NEW

logger = logging.getLogger(__name__)

_AVAILABLE_FUND = 0.0


def fetch_available_fund() -> float:
    try:
        r = dhan.get_fund_limits()
        data = r.get("data", {})
        return float(data.get("availabelBalance", 0))
    except Exception:
        logger.exception("❌ Failed to fetch fund limits")
        return 0.0


def init_fund_cache(force=False) -> float:
    global _AVAILABLE_FUND

    if force or _AVAILABLE_FUND <= 0:
        _AVAILABLE_FUND = fetch_available_fund()

        if _AVAILABLE_FUND <= 0:
            logger.warning("⚠️ Available fund is zero")
        else:
            logger.info(f"💰 Fund initialized: {_AVAILABLE_FUND}")

    return _AVAILABLE_FUND

# ==============================
# MSTOCK FUND (NEW FUNCTION)
# ==============================
_MSTOCK_AVAILABLE_FUND = 0.0


def fetch_mstock_fund() -> float:
    try:
        response = mstock.get_fund_summary()
        data = response.json()

        #logger.info(f" mStock Fund Raw Response: {data}")

        if data.get("status") != "success":
            logger.error("❌ mStock Fund API failed")
            return 0.0

        fund_list = data.get("data", [])

        if not fund_list:
            logger.error("❌ mStock Fund data empty")
            return 0.0

        fund_data = fund_list[0]

        return float(fund_data.get("AVAILABLE_BALANCE", 0))

    except Exception:
        logger.exception("❌ Failed to fetch mStock fund")
        return 0.0


def init_mstock_fund_cache(force=False) -> float:
    global _MSTOCK_AVAILABLE_FUND

    if force or _MSTOCK_AVAILABLE_FUND <= 0:
        _MSTOCK_AVAILABLE_FUND = fetch_mstock_fund()

        if _MSTOCK_AVAILABLE_FUND <= 0:
            logger.warning("⚠️ mStock Available fund is zero")
        else:
            logger.info(f" mStock Fund initialized: {_MSTOCK_AVAILABLE_FUND}")

    return _MSTOCK_AVAILABLE_FUND


def get_mstock_cached_fund(refresh=False) -> float:
    return init_mstock_fund_cache(force=refresh)

def get_cached_fund(refresh=False) -> float:
    return init_fund_cache(force=refresh)
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG)

    print("💡 Testing fund_manager.py locally")
     # Test fetch_available_fund
    fund = fetch_available_fund()
    print(f"fetch_available_fund(): {fund}")

    # Test init_fund_cache
    fund_cached = init_fund_cache(force=True)
    print(f"init_fund_cache(force=True): {fund_cached}")

    # Test get_cached_fund
    fund_cached2 = get_cached_fund(refresh=True)
    print(f"get_cached_fund(refresh=True): {fund_cached2}")


