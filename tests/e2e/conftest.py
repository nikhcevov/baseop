from datetime import UTC, datetime

import pytest

from baseop.bank import Bank
from baseop.clock import FrozenClock

DEMO_DAY = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
DEMO_NIGHT = datetime(2026, 1, 1, 3, 0, tzinfo=UTC)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(DEMO_DAY)


@pytest.fixture
def bank(clock: FrozenClock) -> Bank:
    return Bank(clock=clock)


@pytest.fixture
def day() -> datetime:
    return DEMO_DAY


@pytest.fixture
def night() -> datetime:
    return DEMO_NIGHT
