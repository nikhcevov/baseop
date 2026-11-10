from collections.abc import Callable
from datetime import datetime, timedelta

from baseop.config import APP_TIMEZONE

Clock = Callable[[], datetime]
"""Current-time source; replace it with a deterministic clock in tests."""


def system_now() -> datetime:
    """Current time in the application timezone."""
    return datetime.now(APP_TIMEZONE)


class FrozenClock:
    """Mutable deterministic clock for tests and demos."""

    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def __call__(self) -> datetime:
        return self._moment

    def set(self, moment: datetime) -> None:
        self._moment = moment

    def advance(self, delta: timedelta) -> None:
        self._moment += delta
