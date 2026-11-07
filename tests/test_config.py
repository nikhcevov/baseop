from datetime import datetime, time

import pytest

from baseop.config import APP_TIMEZONE, is_within_window

_CLOSED_FROM = time(0, tzinfo=APP_TIMEZONE)
_CLOSED_TO = time(5, tzinfo=APP_TIMEZONE)


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [(0, 0, True), (4, 59, True), (5, 0, False), (12, 0, False)],
)
def test_half_open_window(hour: int, minute: int, expected: bool) -> None:
    moment = datetime(2026, 1, 1, hour, minute, tzinfo=APP_TIMEZONE)

    assert is_within_window(moment, _CLOSED_FROM, _CLOSED_TO) is expected


def test_window_wraps_past_midnight() -> None:
    start = time(23, tzinfo=APP_TIMEZONE)
    end = time(5, tzinfo=APP_TIMEZONE)

    assert is_within_window(
        datetime(2026, 1, 1, 23, 30, tzinfo=APP_TIMEZONE), start, end
    )
    assert is_within_window(datetime(2026, 1, 1, 2, 0, tzinfo=APP_TIMEZONE), start, end)
    assert not is_within_window(
        datetime(2026, 1, 1, 12, 0, tzinfo=APP_TIMEZONE), start, end
    )
