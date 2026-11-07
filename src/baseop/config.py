from datetime import UTC, datetime, time
from typing import Literal

APP_TIMEZONE = UTC
"""Intentional assumption"""


def is_within_window(moment: datetime, start: time, end: time) -> bool:
    """Checks moment falls into half-open [start, end) window in APP_TIMEZONE.

    Window wraps past midnight when start > end, so 23:00-05:00 covers
    both late evening and early morning.
    """
    current = moment.astimezone(APP_TIMEZONE).timetz()
    if start <= end:
        return start <= current < end
    return current >= start or current < end


Currency = Literal["RUB", "USD", "EUR", "KZT", "CNY"]

RATES_TO_RUB: dict[Currency, float] = {
    "RUB": 1.0,
    "USD": 90.0,
    "EUR": 100.0,
    "KZT": 0.20,
    "CNY": 12.0,
}


def round_money(amount: float) -> float:
    return round(amount, 2)


def convert(
    amount: float,
    source: Currency,
    target: Currency,
) -> float:
    """Converts source currency to target"""
    rate_to_rub = amount * RATES_TO_RUB[source]
    return rate_to_rub / RATES_TO_RUB[target]
