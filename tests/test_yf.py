# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

import calendar
from datetime import date

import pytest

from orcaset import YF


@pytest.mark.parametrize(
    ("dt1", "dt2", "days"),
    [
        # Plain months.
        (date(2027, 1, 15), date(2027, 2, 15), 30),
        (date(2027, 1, 1), date(2028, 1, 1), 360),
        # d1 = 31 becomes 30; d2 = 31 becomes 30 only when d1 is 30 or 31.
        (date(2027, 1, 31), date(2027, 3, 31), 60),
        (date(2027, 1, 30), date(2027, 3, 31), 60),
        (date(2027, 1, 29), date(2027, 3, 31), 62),
        (date(2027, 1, 31), date(2027, 4, 30), 90),
        # End of February as d1 becomes 30, before the d2 = 31 rule.
        (date(2027, 2, 28), date(2027, 3, 31), 30),
        (date(2028, 2, 29), date(2028, 3, 31), 30),
        (date(2027, 2, 28), date(2027, 3, 30), 30),
        # End of February as d2 stays put unless d1 is also end of February.
        (date(2027, 1, 31), date(2027, 2, 28), 28),
        (date(2028, 1, 31), date(2028, 2, 29), 29),
        (date(2027, 2, 28), date(2028, 2, 29), 360),
        (date(2028, 2, 29), date(2029, 2, 28), 360),
        # Feb 28 in a leap year isn't the end of February.
        (date(2028, 2, 28), date(2028, 3, 31), 33),
        # Whole year.
        (date(2026, 12, 31), date(2027, 12, 31), 360),
    ],
)
def test_thirty360_us(dt1: date, dt2: date, days: int):
    assert YF.thirty360(dt1, dt2) * 360 == pytest.approx(days)
    assert YF.thirty360(dt2, dt1) * 360 == pytest.approx(-days)


# Under 30/360 US, month-end periods don't sum to 360: Jan 31 -> end of February
# counts actual February days, and end of February -> Mar 31 counts 30.
@pytest.mark.parametrize(("year", "days"), [(2027, 358), (2028, 359)])
def test_thirty360_month_end_periods(year: int, days: int):
    ends = [date(year, m, calendar.monthrange(year, m)[1]) for m in range(1, 13)]
    starts = [date(year - 1, 12, 31), *ends[:-1]]
    total = sum(YF.thirty360(s, e) * 360 for s, e in zip(starts, ends))
    assert total == pytest.approx(days)
