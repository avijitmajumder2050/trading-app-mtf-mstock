# app/utils/trading_days.py
from datetime import date

import numpy as np
import pandas as pd

# NSE equity holidays on weekdays. 2026 dates up to Oct are taken from
# missing sessions in the EOD data; add the rest from the NSE circular.
NSE_HOLIDAYS = [
    "2026-01-15", "2026-01-26", "2026-03-03", "2026-03-26", "2026-03-31",
    "2026-04-03", "2026-04-14", "2026-05-01", "2026-05-28", "2026-06-26",
    "2026-09-14", "2026-10-02", "2026-10-20",
    "2026-12-25",
]


def trading_day_number(entry_date, today=None) -> int:
    """Session number of `today` in a trade's life; the entry day is day 1."""
    start = pd.to_datetime(entry_date, errors="coerce")
    if pd.isna(start):
        return 0
    today = today or date.today()
    end = pd.Timestamp(today) + pd.Timedelta(days=1)
    return int(np.busday_count(start.date(), end.date(), holidays=NSE_HOLIDAYS))


def is_trading_day(day=None) -> bool:
    day = day or date.today()
    return bool(np.is_busday(day, holidays=NSE_HOLIDAYS))
