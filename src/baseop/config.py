from datetime import UTC
from typing import Literal

APP_TIMEZONE = UTC
"""Intentional assumption"""

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
